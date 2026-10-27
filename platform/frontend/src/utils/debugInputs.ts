/** Validate only explicit output inputs; the server remains authoritative for resources and contracts. */
export function debugInputs(step: Record<string, unknown>, text: string): Record<string, unknown> {
  const inputs: unknown = JSON.parse(text);
  if (!inputs || typeof inputs !== 'object' || Array.isArray(inputs)) throw new Error('前置输入必须为步骤 ID 到字段对象的映射');
  const mapping = inputs as Record<string, unknown>;
  const requirePath = (path: string) => {
    let current: unknown = mapping;
    for (const key of path.split('.')) {
      if (!current || typeof current !== 'object' || !Object.prototype.hasOwnProperty.call(current, key)) throw new Error(`缺少前置输入 outputs.${path}；请显式补充，不会自动执行前置步骤。`);
      current = (current as Record<string, unknown>)[key];
    }
  };
  for (const id of (step.depends_on || []) as string[]) {
    requirePath(id);
    if (!mapping[id] || typeof mapping[id] !== 'object' || Array.isArray(mapping[id])) throw new Error(`前置输入 ${id} 必须为字段对象`);
  }
  // Extraction targets write this step's outputs; they are not required inputs.
  const { extractors: _extractors, ...readFields } = step;
  const source = JSON.stringify(readFields);
  for (const match of source.matchAll(/outputs\.([\w-]+(?:\.[\w-]+)+)/g)) requirePath(match[1]!);
  return mapping;
}
