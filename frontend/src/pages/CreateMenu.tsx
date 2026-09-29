import { useNavigate } from "react-router-dom";
import { Card, Page } from "../components/ui";

const ITEMS = [
  { to: "/create/text?mode=new", emoji: "✍️", title: "새 계약서 작성", desc: "빈 화면에서 직접 써요", id: "new" },
  { to: "/create/pdf", emoji: "📄", title: "내 PDF 불러오기", desc: "가지고 있는 계약서 PDF 에 빈칸을 만들어요", id: "pdf" },
  { to: "/create/text?mode=paste", emoji: "📋", title: "텍스트 붙여넣기", desc: "복사한 계약서 내용을 붙여넣어요", id: "paste" },
  { to: "/create/template", emoji: "🗂️", title: "템플릿 선택", desc: "차용증·용역·근로·거래 계약서", id: "template" },
];

export default function CreateMenu() {
  const nav = useNavigate();
  return (
    <Page title="계약 만들기">
      <p className="mt-2 mb-6 text-[22px] leading-8 font-bold">어떻게 시작할까요?</p>
      <div className="flex flex-col gap-3">
        {ITEMS.map((it) => (
          <Card key={it.id} testid={`create-${it.id}`} onClick={() => nav(it.to)} className="flex items-center gap-4">
            <span className="text-[30px]">{it.emoji}</span>
            <div>
              <p className="text-[17px] font-semibold">{it.title}</p>
              <p className="mt-0.5 text-[14px] text-grey-600">{it.desc}</p>
            </div>
          </Card>
        ))}
      </div>
    </Page>
  );
}
