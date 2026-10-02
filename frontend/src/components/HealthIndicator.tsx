import type { HealthStatus } from '../types';

interface Props {
  health: HealthStatus | null;
  lastChecked: Date | null;
}

export default function HealthIndicator({ health, lastChecked }: Props) {
  const missing = health
    ? [
        health.model_available === false && health.model,
        health.embeddings_model_available === false && health.embeddings_model,
      ].filter(Boolean)
    : [];

  let label = 'Conectando…';
  let detail = '';
  let tone = 'pending';
  if (lastChecked) {
    if (!health) {
      [label, tone, detail] = ['Sin backend', 'down', 'El backend no responde en el puerto 5000'];
    } else if (health.ollama !== 'connected') {
      [label, tone, detail] = ['Sin Ollama', 'down', 'Ollama no responde: ejecuta "ollama serve"'];
    } else if (missing.length) {
      [label, tone, detail] = ['Falta un modelo', 'warn', `Descárgalo con: ollama pull ${missing.join(' / ')}`];
    } else {
      [label, tone, detail] = ['Listo', 'up', `Modelo: ${health.model}`];
    }
  }

  return (
    <div className={`health health--${tone}`} role="status" aria-live="polite" title={detail}>
      <span className="health-dot" aria-hidden="true" />
      <span>{label}</span>
      {detail && tone !== 'up' && <span className="health-detail">{detail}</span>}
    </div>
  );
}
