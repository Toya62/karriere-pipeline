export function renderSparklineSvg(
  points: number[],
  label: string,
  width = 88,
  height = 22
): string {
  const safePoints = points.length >= 2 ? points : [0, points[0] ?? 0];
  const min = Math.min(...safePoints);
  const max = Math.max(...safePoints);
  const span = max - min || 1;
  const padY = 2;

  const coords = safePoints
    .map((val, idx) => {
      const x = (idx / (safePoints.length - 1)) * width;
      const y = height - padY - ((val - min) / span) * (height - padY * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const safeLabel = label.replace(/[<>&"]/g, "");
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${safeLabel}">
    <title>${safeLabel}</title>
    <polyline points="${coords}" fill="none" stroke="var(--accent)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
  </svg>`;
}

