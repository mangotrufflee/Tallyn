function KPICard({
  title,
  value,
  description,
  subtitle,
  type = "neutral",
  icon,
}) {
  const footer = description ?? subtitle;
  return (
    <div className="kpi-card">
      <div className="kpi-top">
        <span className="kpi-title">{title}</span>

        <div className={`kpi-icon ${type}`}>
          {icon}
        </div>
      </div>

      <div className="kpi-value">
        {value}
      </div>

      <div className={`kpi-footer ${type}-text`}>
        {footer}
      </div>
    </div>
  );
}

export default KPICard;