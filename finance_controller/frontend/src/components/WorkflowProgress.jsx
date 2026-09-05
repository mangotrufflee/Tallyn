const STEPS = [
  { number: "01", label: "Upload" },
  { number: "02", label: "Validate" },
  { number: "03", label: "Reconcile" },
  { number: "04", label: "Review" },
  { number: "05", label: "Complete" },
];

export default function WorkflowProgress({ currentStep = 1, hint = "" }) {
  return (
    <div className="workflow-progress">
      <div className="workflow-progress-track">
        {STEPS.map((step, index) => {
          const stepIndex = index + 1;
          const state =
            stepIndex < currentStep
              ? "is-done"
              : stepIndex === currentStep
                ? "is-current"
                : "is-upcoming";

          return (
            <div key={step.label} className="workflow-progress-item-wrap">
              <div className={`workflow-progress-item ${state}`}>
                <span className="workflow-progress-number">{step.number}</span>
                <strong>{step.label}</strong>
              </div>
              {index < STEPS.length - 1 && (
                <span className="workflow-progress-arrow">→</span>
              )}
            </div>
          );
        })}
      </div>
      {hint && <p className="workflow-progress-hint">{hint}</p>}
    </div>
  );
}
