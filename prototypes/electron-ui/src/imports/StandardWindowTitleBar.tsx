function Close() {
  return (
    <div className="bg-[#ff736a] relative rounded-[100px] shrink-0 size-[14px]" data-name="Close">
      <div aria-hidden="true" className="absolute border-[0.5px] border-[rgba(0,0,0,0.1)] border-solid inset-0 pointer-events-none rounded-[100px]" />
    </div>
  );
}

function Minimize() {
  return (
    <div className="bg-[#febc2e] relative rounded-[100px] shrink-0 size-[14px]" data-name="Minimize">
      <div aria-hidden="true" className="absolute border-[0.5px] border-[rgba(0,0,0,0.1)] border-solid inset-0 pointer-events-none rounded-[100px]" />
    </div>
  );
}

function Zoom() {
  return (
    <div className="bg-[#19c332] relative rounded-[100px] shrink-0 size-[14px]" data-name="Zoom">
      <div aria-hidden="true" className="absolute border-[0.5px] border-[rgba(0,0,0,0.1)] border-solid inset-0 pointer-events-none rounded-[100px]" />
    </div>
  );
}

function Frame() {
  return (
    <div className="content-stretch flex gap-[3px] items-center relative shrink-0 text-[15px] whitespace-nowrap">
      <div className="flex flex-col font-['SF_Pro:Semibold',sans-serif] font-[590] justify-center leading-[0] relative shrink-0 text-[rgba(0,0,0,0.5)] text-center" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss15'" }}>
        <p className="leading-[16px]">􀈕</p>
      </div>
      <p className="font-['SF_Pro:Bold',sans-serif] font-bold leading-[16px] relative shrink-0 text-[rgba(0,0,0,0.85)]" style={{ fontVariationSettings: "'wdth' 100" }}>
        Title
      </p>
    </div>
  );
}

export default function StandardWindowTitleBar() {
  return (
    <div className="content-stretch flex gap-[16px] items-center p-[8px] relative size-full" data-name="Standard Window/Title Bar">
      <div className="content-stretch flex gap-[9px] items-center p-px relative shrink-0" data-name="Window Controls">
        <Close />
        <Minimize />
        <Zoom />
      </div>
      <div className="content-stretch flex flex-col gap-[2px] items-start justify-center relative shrink-0" data-name="Title">
        <Frame />
      </div>
    </div>
  );
}