import { type ReactNode, useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

/** PDF 한 페이지를 canvas 로 그리고, 그 위에 children(오버레이)을 올린다. 좌표는 페이지 대비 비율(%) */
export function usePdf(data: ArrayBuffer | null) {
  const [doc, setDoc] = useState<pdfjs.PDFDocumentProxy | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    const task = pdfjs.getDocument({ data: new Uint8Array(data.slice(0)), isEvalSupported: false });
    task.promise.then((d) => !cancelled && setDoc(d)).catch(() => !cancelled && setErr("PDF 를 표시하지 못했어요."));
    return () => {
      cancelled = true;
      task.destroy();
    };
  }, [data]);
  return { doc, err };
}

export function PdfPage({ doc, pageNo, children, onPointerDown, testid }: {
  doc: pdfjs.PDFDocumentProxy; pageNo: number; children?: ReactNode; onPointerDown?: (e: React.PointerEvent<HTMLDivElement>) => void; testid?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [ratio, setRatio] = useState(1.414);
  useEffect(() => {
    let task: pdfjs.RenderTask | null = null;
    let cancelled = false;
    doc.getPage(pageNo).then((page) => {
      if (cancelled || !canvasRef.current) return;
      const vp1 = page.getViewport({ scale: 1 });
      setRatio(vp1.height / vp1.width);
      const cssWidth = canvasRef.current.parentElement?.clientWidth || 360;
      const scale = (cssWidth / vp1.width) * Math.min(window.devicePixelRatio || 1, 2);
      const vp = page.getViewport({ scale });
      const c = canvasRef.current;
      c.width = vp.width;
      c.height = vp.height;
      task = page.render({ canvasContext: c.getContext("2d")!, viewport: vp });
      task.promise.catch(() => {});
    });
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [doc, pageNo]);
  return (
    <div data-testid={testid} className="relative w-full touch-none overflow-hidden rounded-xl border border-grey-200 bg-white shadow-sm select-none" style={{ aspectRatio: `1 / ${ratio}` }} onPointerDown={onPointerDown}>
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
      <div className="absolute inset-0">{children}</div>
    </div>
  );
}
