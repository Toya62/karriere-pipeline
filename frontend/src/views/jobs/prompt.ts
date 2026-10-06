/** Copy-for-AI prompt construction (mirrors the legacy "detailed" template). */

import type { JobRecord } from "../../api/types";

/** Drop boilerplate lines from a job description before sending it to an LLM. */
export function cleanDescriptionForAI(text: string | null | undefined): string {
  if (!text) return "No description provided.";
  const lines = text.split("\n").map((line) => line.trim());
  const cleaned = lines.filter((line) => {
    if (line.length === 0) return false;
    if (line.startsWith("*") || line.startsWith("-") || line.startsWith("•")) return true;
    if (/^[0-9]+\./.test(line)) return true;
    if (line.length > 80) return true;
    if (/[.!?:]$/.test(line)) return true;
    if (/(require|muss|task|aufgab|skill)/i.test(line)) return true;
    return line.length >= 45;
  });
  const result = cleaned.join("\n");
  return result.length > 20000 ? `${result.substring(0, 20000)}\n... [Truncated for length]` : result;
}

export function buildAiPrompt(jobs: JobRecord[]): string {
  if (jobs.length === 0) return "";

  let output = "Here are the selected job listings details:\n\n";
  jobs.forEach((job, index) => {
    output += `=== Job ${index + 1}: ${job.title} at ${job.company} ===\n`;
    output += `- Company: ${job.company}\n`;
    output += `- Location: ${job.location || "N/A"}\n`;
    if (job.ai_score) output += `- AI Score Match: ${job.ai_score}/10\n`;
    if (job.ai_reason) output += `- AI Evaluation: ${job.ai_reason}\n`;
    if (job.matched_skills) output += `- Matched Skills: ${job.matched_skills}\n`;
    if (job.job_url) output += `- URL: ${job.job_url}\n`;
    output += `- Job Description:\n${cleanDescriptionForAI(job.description)}\n\n`;
  });
  return output;
}
