// ── Low-level Canvas2D drawing helpers for the solar system ──

export interface EllipseOpts {
  stroke: string;
  lineWidth: number;
  dash?: number[];
}

export function drawEllipse(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  opts: EllipseOpts,
) {
  ctx.save();
  ctx.beginPath();
  ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
  ctx.strokeStyle = opts.stroke;
  ctx.lineWidth = opts.lineWidth;
  if (opts.dash) ctx.setLineDash(opts.dash);
  ctx.stroke();
  ctx.restore();
}

export function drawGlow(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  color: string,
  intensity: number,
) {
  const grad = ctx.createRadialGradient(x, y, 0, x, y, radius);
  grad.addColorStop(0, `rgba(${color},${0.6 * intensity})`);
  grad.addColorStop(0.4, `rgba(${color},${0.25 * intensity})`);
  grad.addColorStop(1, `rgba(${color},0)`);
  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, Math.PI * 2);
  ctx.fillStyle = grad;
  ctx.fill();
  ctx.restore();
}

export function drawBufferRing(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  nodeRadius: number,
  thickness: number,
  color: string,
  rotation: number,
) {
  if (thickness <= 0) return;
  const ringRx = nodeRadius + 8 + thickness * 0.5;
  const ringRy = ringRx * 0.35;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(rotation);
  ctx.beginPath();
  ctx.ellipse(0, 0, ringRx, ringRy, 0, 0, Math.PI * 2);
  ctx.strokeStyle = color;
  ctx.lineWidth = thickness;
  ctx.stroke();
  ctx.restore();
}

export interface TrailParticle {
  x: number;
  y: number;
  alpha: number;
  size: number;
  color: string;
}

export function drawParticleTrail(
  ctx: CanvasRenderingContext2D,
  particles: TrailParticle[],
) {
  ctx.save();
  for (const p of particles) {
    if (p.alpha <= 0) continue;
    ctx.globalAlpha = p.alpha;
    ctx.fillStyle = p.color;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

export function drawMessageBeam(
  ctx: CanvasRenderingContext2D,
  from: { x: number; y: number },
  to: { x: number; y: number },
  progress: number,
  color: string,
) {
  const cpX = (from.x + to.x) / 2;
  const cpY = Math.min(from.y, to.y) - 40;

  // Compute point along quadratic bezier
  const t = Math.min(progress, 1);
  const headX = (1 - t) ** 2 * from.x + 2 * (1 - t) * t * cpX + t ** 2 * to.x;
  const headY = (1 - t) ** 2 * from.y + 2 * (1 - t) * t * cpY + t ** 2 * to.y;

  // Draw trail
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.quadraticCurveTo(cpX, cpY, headX, headY);
  const fadeAlpha = progress > 1 ? Math.max(0, 1 - (progress - 1) * 5) : 1;
  ctx.strokeStyle = color;
  ctx.globalAlpha = 0.4 * fadeAlpha;
  ctx.lineWidth = 2;
  ctx.stroke();

  // Draw glowing head
  if (t <= 1) {
    ctx.globalAlpha = fadeAlpha;
    const grad = ctx.createRadialGradient(headX, headY, 0, headX, headY, 8);
    grad.addColorStop(0, color);
    grad.addColorStop(1, "transparent");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(headX, headY, 8, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

export function drawStarCorona(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  baseRadius: number,
  phase: number,
  color: string,
) {
  ctx.save();
  const layers = [
    { rMul: 1.4, alpha: 0.35 },
    { rMul: 2.0, alpha: 0.18 },
    { rMul: 2.8, alpha: 0.08 },
    { rMul: 3.6, alpha: 0.03 },
  ];
  for (let i = 0; i < layers.length; i++) {
    const l = layers[i];
    const r = baseRadius * l.rMul + Math.sin(phase + i * 0.7) * baseRadius * 0.15;
    const grad = ctx.createRadialGradient(x, y, baseRadius * 0.3, x, y, r);
    grad.addColorStop(0, `rgba(${color},${l.alpha})`);
    grad.addColorStop(1, `rgba(${color},0)`);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();
  }
  ctx.restore();
}
