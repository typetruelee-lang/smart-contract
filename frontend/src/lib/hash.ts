// 브라우저에서 파일 SHA-256 계산 — 계약서 원본을 서버로 보내지 않고 디지털 지문만 전송한다.
export async function sha256Hex(data: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function sha256File(file: File): Promise<string> {
  return sha256Hex(await file.arrayBuffer());
}
