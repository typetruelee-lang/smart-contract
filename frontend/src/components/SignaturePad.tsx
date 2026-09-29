import { useEffect, useRef, useState } from "react";

/** 손글씨 서명 패드 — PNG data URL 을 돌려준다. */
export function SignaturePad({ onChange }: { onChange: (dataUrl: string | null) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const last = useRef<{ x: number; y: number } | null>(null);
  const strokes = useRef(0);
  const [empty, setEmpty] = useState(true);

  useEffect(() => {
    const c = ref.current!;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = c.clientWidth * dpr;
    c.height = c.clientHeight * dpr;
    const ctx = c.getContext("2d")!;
    ctx.scale(dpr, dpr);
    ctx.lineWidth = 3;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#191f28";
  }, []);

  function pos(e: React.PointerEvent) {
    const r = ref.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }
  function down(e: React.PointerEvent) {
    drawing.current = true;
    last.current = pos(e);
    ref.current!.setPointerCapture(e.pointerId);
  }
  function move(e: React.PointerEvent) {
    if (!drawing.current || !last.current) return;
    const p = pos(e);
    const ctx = ref.current!.getContext("2d")!;
    ctx.beginPath();
    ctx.moveTo(last.current.x, last.current.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    last.current = p;
    strokes.current += 1;
  }
  function up() {
    if (!drawing.current) return;
    drawing.current = false;
    if (strokes.current > 8) {
      setEmpty(false);
      onChange(exportPng());
    }
  }
  function exportPng(): string {
    // 서버 용량 제한을 넘지 않도록 최대 600px 폭으로 줄여서 내보낸다
    const src = ref.current!;
    const w = Math.min(600, src.width);
    const h = Math.round((src.height / src.width) * w);
    const out = document.createElement("canvas");
    out.width = w;
    out.height = h;
    out.getContext("2d")!.drawImage(src, 0, 0, w, h);
    return out.toDataURL("image/png");
  }
  function clear() {
    const c = ref.current!;
    c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
    strokes.current = 0;
    setEmpty(true);
    onChange(null);
  }

  return (
    <div>
      <div className="relative">
        <canvas ref={ref} data-testid="signature-pad" className="h-48 w-full touch-none rounded-2xl border-2 border-dashed border-grey-300 bg-grey-50"
          onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onPointerLeave={up} aria-label="서명 입력 영역" />
        {empty && <span className="pointer-events-none absolute inset-0 grid place-items-center text-grey-400">여기에 서명해 주세요</span>}
      </div>
      <div className="mt-2 text-right">
        <button className="text-[14px] text-grey-600 underline" onClick={clear} data-testid="signature-clear">다시 쓰기</button>
      </div>
    </div>
  );
}
