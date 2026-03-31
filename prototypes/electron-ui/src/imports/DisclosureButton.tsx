function Black() {
  return <div className="absolute bg-black inset-0 opacity-5" data-name="Black" />;
}

export default function DisclosureButton() {
  return (
    <div className="content-stretch flex flex-col items-center justify-end overflow-clip relative rounded-[1000px] size-full" data-name="Disclosure Button">
      <div className="absolute left-0 overflow-clip size-[16px] top-0" data-name="BG">
        <Black />
      </div>
      <div className="flex flex-col font-['SF_Pro:Bold',sans-serif] font-bold h-[16px] justify-center leading-[0] min-w-full relative shrink-0 text-[10px] text-[rgba(0,0,0,0.85)] text-center w-[min-content]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[normal]">􀆈</p>
      </div>
    </div>
  );
}