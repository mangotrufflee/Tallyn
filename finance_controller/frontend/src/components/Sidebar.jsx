function KPICard({
  title,
  value,
  description,
  type = "neutral",
  icon,
}) {
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
        {description}
      </div>
    </div>
  );
}

export default KPICard;