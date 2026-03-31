export default function Tooltip() {
  return (
    <div className="backdrop-blur-[10px] bg-[rgba(246,246,246,0.72)] content-stretch flex items-center overflow-clip pb-[2px] pt-[3px] px-[6px] relative rounded-[1px] shadow-[0px_1px_3px_0px_rgba(0,0,0,0.2)] size-full" data-name="Tooltip">
      <p className="font-['SF_Pro:Medium',sans-serif] font-[510] leading-[13px] relative shrink-0 text-[#4d4d4d] text-[11px] whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
        This is a tooltip.
      </p>
    </div>
  );
}