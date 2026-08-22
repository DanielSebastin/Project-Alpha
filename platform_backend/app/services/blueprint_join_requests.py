import uuid
from datetime import datetime, timezone
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.blueprint import (
    Blueprint,
    BlueprintSlot,
    BlueprintMember,
    BlueprintMemberRole,
    BlueprintJoinRequest,
    BlueprintJoinRequestStatus,
    BlueprintStatus,
    SlotStatus,
)
from app.models.user import User


class BlueprintJoinError(Exception):
    pass

def create_join_request(db: Session, blueprint_id: uuid.UUID, requester: User) -> BlueprintJoinRequest:
    blueprint = db.query(Blueprint).filter(Blueprint.id == blueprint_id).first()
    if not blueprint:
        raise BlueprintJoinError("Blueprint not found")
        
    if blueprint.status not in (BlueprintStatus.OPEN, BlueprintStatus.FORMING):
        raise BlueprintJoinError("Blueprint is not accepting join requests")
        
    if blueprint.owner_id == requester.id:
        raise BlueprintJoinError("You cannot join your own blueprint")

    # Ensure requester is not already in the blueprint
    existing_member = db.query(BlueprintMember).filter(
        BlueprintMember.blueprint_id == blueprint_id,
        BlueprintMember.user_id == requester.id
    ).first()
    if existing_member:
        raise BlueprintJoinError("You are already a member of this blueprint")
        
    # Ensure no duplicate pending request
    duplicate = db.query(BlueprintJoinRequest).filter(
        BlueprintJoinRequest.blueprint_id == blueprint_id,
        BlueprintJoinRequest.user_id == requester.id,
        BlueprintJoinRequest.status == BlueprintJoinRequestStatus.PENDING,
    ).first()
    if duplicate:
        raise BlueprintJoinError("You already have a pending join request for this blueprint")
        

        
    req = BlueprintJoinRequest(
        blueprint_id=blueprint_id,
        user_id=requester.id,
        status=BlueprintJoinRequestStatus.PENDING,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req

def accept_join_request(db: Session, request_id: uuid.UUID, slot_id: uuid.UUID, owner: User) -> BlueprintJoinRequest:
    req = db.query(BlueprintJoinRequest).filter(BlueprintJoinRequest.id == request_id).first()
    if not req:
        raise BlueprintJoinError("Join request not found")
        
    if req.status != BlueprintJoinRequestStatus.PENDING:
        raise BlueprintJoinError("Join request is not pending")
        
    blueprint = db.query(Blueprint).filter(Blueprint.id == req.blueprint_id).first()
    if not blueprint or blueprint.owner_id != owner.id:
        raise BlueprintJoinError("Only the owner can accept join requests")
        
    # Lock the slot
    slot = db.query(BlueprintSlot).filter(BlueprintSlot.id == slot_id).with_for_update().first()
    if not slot or slot.blueprint_id != req.blueprint_id:
        raise BlueprintJoinError("Slot not found in this blueprint")
        
    if slot.status != SlotStatus.OPEN:
        raise BlueprintJoinError("This slot has already been filled")
        
    # Check if user is already a member
    existing_member = db.query(BlueprintMember).filter(
        BlueprintMember.blueprint_id == req.blueprint_id,
        BlueprintMember.user_id == req.user_id
    ).first()
    if existing_member:
        raise BlueprintJoinError("Candidate is already a member")
        
    # Mark slot filled
    slot.status = SlotStatus.FILLED
    
    # Accept request
    req.status = BlueprintJoinRequestStatus.ACCEPTED
    
    # Add member
    member = BlueprintMember(
        blueprint_id=req.blueprint_id,
        user_id=req.user_id,
        slot_id=slot.id,
        role=BlueprintMemberRole.MEMBER
    )
    db.add(member)
    
    # Re-fetch blueprint with lock to update status safely
    locked_bp = db.query(Blueprint).filter(Blueprint.id == req.blueprint_id).with_for_update().first()
    db.flush()
    
    all_filled = True
    for s in locked_bp.slots:
        if s.status == SlotStatus.OPEN:
            all_filled = False
            break
            
    if all_filled:
        locked_bp.status = BlueprintStatus.FULL
    else:
        locked_bp.status = BlueprintStatus.FORMING
        
    db.commit()
    db.refresh(req)
    return req
    
def reject_join_request(db: Session, request_id: uuid.UUID, owner: User) -> BlueprintJoinRequest:
    req = db.query(BlueprintJoinRequest).filter(BlueprintJoinRequest.id == request_id).first()
    if not req:
        raise BlueprintJoinError("Join request not found")
        
    blueprint = db.query(Blueprint).filter(Blueprint.id == req.blueprint_id).first()
    if not blueprint or blueprint.owner_id != owner.id:
        raise BlueprintJoinError("Only the owner can reject join requests")
        
    if req.status != BlueprintJoinRequestStatus.PENDING:
        raise BlueprintJoinError("Join request is not pending")
        
    req.status = BlueprintJoinRequestStatus.REJECTED
    db.commit()
    db.refresh(req)
    return req

def list_blueprints_for_discovery(db: Session, hackathon_id: str, limit: int = 50) -> List[Blueprint]:
    return (
        db.query(Blueprint)
        .filter(
            Blueprint.hackathon_id == hackathon_id,
            Blueprint.status.in_([BlueprintStatus.OPEN, BlueprintStatus.FORMING])
        )
        .order_by(Blueprint.created_at.desc())
        .limit(limit)
        .all()
    )

def lock_blueprint(db: Session, blueprint_id: uuid.UUID, owner: User) -> Blueprint:
    bp = db.query(Blueprint).filter(Blueprint.id == blueprint_id).first()
    if not bp:
        raise BlueprintJoinError("Blueprint not found")
    if bp.owner_id != owner.id:
        raise BlueprintJoinError("Only the owner can lock the blueprint")
    bp.status = BlueprintStatus.LOCKED
    db.commit()
    db.refresh(bp)
    return bp
