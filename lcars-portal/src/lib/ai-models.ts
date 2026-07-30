export interface AIModel {
  id: string;
  label: string;
  description: string;
  available: boolean;
}

export const AI_MODELS: AIModel[] = [
  {
    id: 'glm-5.2',
    label: 'GLM 5.2',
    description: 'Default — balanced capability and speed',
    available: true,
  },
  {
    id: 'kimi-k2.7-code',
    label: 'Kimi K2',
    description: 'Strong reasoning and long-context tasks',
    available: true,
  },
  {
    id: 'qwen3-coder:480b',
    label: 'Qwen3 Coder',
    description: 'Best for code and technical analysis',
    available: true,
  },
];

export const DEFAULT_MODEL_ID = process.env.NEXT_PUBLIC_OLLAMA_MODEL_DEFAULT ?? 'glm-5.2';
