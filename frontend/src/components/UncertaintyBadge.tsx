interface Props {
  value: number;
}

export function UncertaintyBadge({ value }: Props) {
  const percentage = Math.round(value * 100);
  const tone = value > 0.66 ? '#fee2e2' : value > 0.33 ? '#fef3c7' : '#dcfce7';
  const textColor = value > 0.66 ? '#b91c1c' : value > 0.33 ? '#92400e' : '#166534';

  return (
    <span className="badge" style={{ backgroundColor: tone, color: textColor }} aria-label={`Uncertainty ${percentage}%`}>
      {percentage}% uncertain
    </span>
  );
}
