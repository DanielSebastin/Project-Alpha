interface BrandLogoProps {
  size?: number;
  showWordmark?: boolean;
}

const BrandLogo = ({ size = 28, showWordmark = true }: BrandLogoProps) => {
  return (
    <div className="brand">
      <span className="brand-mark" style={{ width: size, height: size }}>
        <img src="/logo1.jpeg" alt="Hack It Up Logo" className="brand-logo-img" />
      </span>
      {showWordmark && <span className="brand-text">Hack It Up</span>}
    </div>
  );
};

export default BrandLogo;
