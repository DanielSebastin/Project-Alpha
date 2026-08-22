import axios from 'axios';

const SERVER_URL = 'http://localhost:8000';
const API_URL = `${SERVER_URL}/api/v1`;

const apiClient = axios.create({
  baseURL: API_URL,
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (config.method === 'get') {
    config.params = { ...config.params, _t: new Date().getTime() };
  }
  return config;
});

// Build a cache-busting absolute URL for a server-relative asset (e.g. /uploads/avatars/x.png)
export const assetUrl = (relativeUrl?: string | null): string | null => {
  if (!relativeUrl) return null;
  const sep = relativeUrl.includes('?') ? '&' : '?';
  return `${SERVER_URL}${relativeUrl}${sep}_=${Date.now()}`;
};

export const api = {
  // Auth
  register: (data: any) => apiClient.post('/auth/register', data),
  login: (data: any) => apiClient.post('/auth/login', data),
  getMe: () => apiClient.get('/auth/me'),

  // Profile
  getProfile: () => apiClient.get('/profile/'),
  createProfile: (data: any) => apiClient.post('/profile/', data),
  updateProfile: (data: any) => apiClient.patch('/profile/', data),
  addSkill: (data: { name: string, level: string }) => apiClient.post('/profile/skills', data),
  getSkills: () => apiClient.get('/profile/skills'),
  deleteSkill: (skillId: string) => apiClient.delete(`/profile/skills/${skillId}`),
  uploadResume: (formData: FormData) => apiClient.post('/profile/resume', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  getVerificationStatus: () => apiClient.get('/profile/verification-status'),

  // Avatar
  uploadAvatar: (formData: FormData) => apiClient.post('/profile/avatar', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  removeAvatar: () => apiClient.delete('/profile/avatar'),

  // Skill Assessment
  startSkillAssessment: () => apiClient.post('/assessment/start'),
  submitSkillAssessment: (data: any) => apiClient.post('/assessment/submit', data),
  getSkillResults: () => apiClient.get('/assessment/results'),
  getSkillSessions: () => apiClient.get('/assessment/sessions'),

  // Collaboration Assessment
  startCollabAssessment: () => apiClient.post('/collaboration/start'),
  submitCollabAssessment: (data: any) => apiClient.post('/collaboration/submit', data),
  getCollabResult: () => apiClient.get('/collaboration/result'),
  getCollabStatus: () => apiClient.get('/collaboration/status'),

  // Personality Assessment
  startPersonalityAssessment: () => apiClient.get('/personality/start'),
  submitPersonalityAssessment: (data: any) => apiClient.post('/personality/submit', data),
  getPersonalityResult: () => apiClient.get('/personality/result'),
  getPersonalityStatus: () => apiClient.get('/personality/status'),

  // Blueprints
  getMyBlueprints: () => apiClient.get('/blueprints/mine'),
  createBlueprint: (data: {
    hackathon_id: string;
    name: string;
    description?: string | null;
    domains: string[];
    slots: { role: string; slot_order: number; skills: string[] }[];
  }) => apiClient.post('/blueprints', data),
  getBlueprintRecommendations: (blueprintId: string) => 
    apiClient.get(`/blueprints/${blueprintId}/recommendations`),
  inviteToBlueprint: (blueprintId: string, data: { receiver_id: string; slot_id: string }) =>
    apiClient.post(`/blueprints/${blueprintId}/invite`, data),
  getBlueprintDashboard: (blueprintId: string) =>
    apiClient.get(`/blueprints/${blueprintId}/dashboard`),
  getMyBlueprintInvitations: () =>
    apiClient.get('/blueprints/my-invitations'),
  acceptBlueprintInvitation: (invitationId: string) =>
    apiClient.post(`/blueprints/invitations/${invitationId}/accept`),
  rejectBlueprintInvitation: (invitationId: string) =>
    apiClient.post(`/blueprints/invitations/${invitationId}/reject`),
  cancelBlueprintInvitation: (invitationId: string) =>
    apiClient.post(`/blueprints/invitations/${invitationId}/cancel`),
  getBlueprints: (hackathonId: string) =>
    apiClient.get(`/blueprints?hackathon_id=${hackathonId}`),
  requestToJoinBlueprint: (blueprintId: string) =>
    apiClient.post(`/blueprints/${blueprintId}/join-requests`),
  acceptBlueprintJoinRequest: (requestId: string, slotId: string) =>
    apiClient.post(`/blueprints/join-requests/${requestId}/accept`, { slot_id: slotId }),
  rejectBlueprintJoinRequest: (requestId: string) =>
    apiClient.post(`/blueprints/join-requests/${requestId}/reject`),
  lockBlueprint: (blueprintId: string) =>
    apiClient.post(`/blueprints/${blueprintId}/lock`),

};
