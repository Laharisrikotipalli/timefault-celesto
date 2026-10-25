export function downloadEvidence(
  runId: string,
  evidence: Record<string, unknown>,
): void {
  const file = new Blob([JSON.stringify(evidence, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(file);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${runId}-evidence.json`;
  link.click();
  URL.revokeObjectURL(url);
}
