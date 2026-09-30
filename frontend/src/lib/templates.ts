// 템플릿 카드의 아이콘·색. 이름과 설명은 서버(/api/templates)가 정한다.
export const TEMPLATE_LOOK: Record<string, { icon: string; tint: string }> = {
  loan: { icon: "💰", tint: "bg-[#fff6e0]" },
  service: { icon: "🛠️", tint: "bg-[#eaf4ff]" },
  goods: { icon: "📦", tint: "bg-[#eefaf1]" },
  employment: { icon: "🧑‍💼", tint: "bg-[#f1efff]" },
  employment_daily: { icon: "🦺", tint: "bg-[#fff1e8]" },
  employment_parttime: { icon: "⏰", tint: "bg-[#e9f8f8]" },
};

export const lookOf = (id: string) => TEMPLATE_LOOK[id] ?? { icon: "📝", tint: "bg-grey-100" };
