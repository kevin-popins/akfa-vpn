import { z } from 'zod';

export const articleSchema = z.object({
  slug: z
    .string()
    .min(1)
    .max(120)
    .regex(/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/, 'Slug должен содержать латиницу, цифры и дефисы без дефиса в начале или конце'),
  title: z.string().min(1).max(180),
  description: z.string().max(500).default(''),
  section: z.string().min(1).max(120),
  sort_order: z.coerce.number().int().min(0).max(100000).default(100),
  status: z.enum(['draft', 'published']).default('draft'),
  content: z.string().default(''),
});
