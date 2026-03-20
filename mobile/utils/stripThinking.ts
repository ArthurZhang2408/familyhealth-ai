/** Strip `[Thinking: ...]` tags from LLM text. Hides trailing incomplete tags during streaming. */
export function stripThinkingTags(text: string): string {
  let result = text.replace(/\[Thinking:[^\]]*\]\s*/g, '');
  result = result.replace(/\[Thinking:[^\]]*$/, '');
  return result;
}
