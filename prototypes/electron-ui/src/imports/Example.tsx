function FillShadow() {
  return (
    <div className="absolute inset-0 rounded-[18px] shadow-[0px_8px_40px_0px_rgba(0,0,0,0.12)]" data-name="Fill + Shadow">
      <div aria-hidden="true" className="absolute inset-0 pointer-events-none rounded-[18px]">
        <div className="absolute bg-[#262626] inset-0 mix-blend-color-dodge rounded-[18px]" />
        <div className="absolute bg-[rgba(245,245,245,0.67)] inset-0 rounded-[18px]" />
      </div>
    </div>
  );
}

function GlassEffect() {
  return <div className="absolute bg-[rgba(0,0,0,0.2)] inset-0 mix-blend-screen rounded-[18px]" data-name="Glass Effect" />;
}

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

function WindowControls() {
  return (
    <div className="h-[32px] relative shrink-0 w-full" data-name="Window Controls">
      <div className="absolute content-stretch flex items-center justify-center px-[7px] py-[3px] right-[10px] rounded-[100px] size-[24px] top-[-4px]" data-name="Button">
        <div className="flex flex-col font-['SF_Pro:Semibold',sans-serif] font-[590] justify-center leading-[0] relative shrink-0 size-[24px] text-[#1a1a1a] text-[10px] text-center" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
          <p className="leading-[12px]">􀏚</p>
        </div>
      </div>
      <div className="absolute content-stretch flex gap-[9px] items-center left-[10px] p-px top-0" data-name="Window Controls">
        <Close />
        <Minimize />
        <Zoom />
      </div>
    </div>
  );
}

function Frame2() {
  return (
    <div className="h-[16px] relative shrink-0 w-[18px]" data-name="Frame">
      <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[#007aff] text-[11px] text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[16px]">􀈕</p>
      </div>
    </div>
  );
}

function Frame1() {
  return (
    <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]" data-name="Frame">
      <div aria-hidden="true" className="absolute bg-[rgba(0,0,0,0.11)] inset-0 mix-blend-multiply pointer-events-none rounded-[8px]" />
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
          <Frame2 />
          <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-[rgba(0,0,0,0.85)] text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[16px] overflow-hidden">Text Edit</p>
          </div>
          <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-[#bfbfbf] text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px]">Detail</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame4() {
  return (
    <div className="h-[16px] relative shrink-0 w-[18px]" data-name="Frame">
      <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[11px] text-[rgba(0,0,0,0.85)] text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[16px]">􀐫</p>
      </div>
    </div>
  );
}

function Frame3() {
  return (
    <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]" data-name="Frame">
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
          <Frame4 />
          <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-[rgba(0,0,0,0.85)] text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[16px] overflow-hidden">Recents</p>
          </div>
          <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-[#bfbfbf] text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px]">Detail</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame6() {
  return (
    <div className="h-[16px] relative shrink-0 w-[18px]" data-name="Frame">
      <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[11px] text-[rgba(0,0,0,0.85)] text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[16px]">􀈝</p>
      </div>
    </div>
  );
}

function Frame5() {
  return (
    <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]" data-name="Frame">
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
          <Frame6 />
          <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-[rgba(0,0,0,0.85)] text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[16px] overflow-hidden">Shared</p>
          </div>
          <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-[#bfbfbf] text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px]">Detail</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame8() {
  return (
    <div className="h-[16px] relative shrink-0 w-[18px]" data-name="Frame">
      <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[11px] text-[rgba(0,0,0,0.85)] text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[16px]">􀣰</p>
      </div>
    </div>
  );
}

function Frame7() {
  return (
    <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]" data-name="Frame">
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
          <Frame8 />
          <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-[rgba(0,0,0,0.85)] text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[16px] overflow-hidden">Desktop</p>
          </div>
          <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-[#bfbfbf] text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px]">Detail</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame10() {
  return (
    <div className="h-[16px] relative shrink-0 w-[18px]" data-name="Frame">
      <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[11px] text-[rgba(0,0,0,0.85)] text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[16px]">􀈷</p>
      </div>
    </div>
  );
}

function Frame9() {
  return (
    <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]" data-name="Frame">
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
          <Frame10 />
          <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-[rgba(0,0,0,0.85)] text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[16px] overflow-hidden">Documents</p>
          </div>
          <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-[#bfbfbf] text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px]">Detail</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame12() {
  return (
    <div className="h-[16px] relative shrink-0 w-[18px]" data-name="Frame">
      <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[11px] text-[rgba(0,0,0,0.85)] text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[16px]">􀁸</p>
      </div>
    </div>
  );
}

function Frame11() {
  return (
    <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]" data-name="Frame">
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
          <Frame12 />
          <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-[rgba(0,0,0,0.85)] text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[16px] overflow-hidden">Downloads</p>
          </div>
          <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-[#bfbfbf] text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px]">Detail</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame14() {
  return (
    <div className="h-[16px] relative shrink-0 w-[18px]" data-name="Frame">
      <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[11px] text-[rgba(0,0,0,0.85)] text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[16px]">􀇂</p>
      </div>
    </div>
  );
}

function Frame13() {
  return (
    <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]" data-name="Frame">
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
          <Frame14 />
          <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-[rgba(0,0,0,0.85)] text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[16px] overflow-hidden">iCloud Drive</p>
          </div>
          <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-[#bfbfbf] text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px]">Detail</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame16() {
  return (
    <div className="h-[16px] relative shrink-0 w-[18px]" data-name="Frame">
      <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[11px] text-[rgba(0,0,0,0.85)] text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[16px]">􀎞</p>
      </div>
    </div>
  );
}

function Frame15() {
  return (
    <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]" data-name="Frame">
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
          <Frame16 />
          <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-[rgba(0,0,0,0.85)] text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[16px] overflow-hidden">janeappleseed</p>
          </div>
          <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-[#bfbfbf] text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px]">Detail</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame18() {
  return (
    <div className="h-[16px] relative shrink-0 w-[18px]" data-name="Frame">
      <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[11px] text-[rgba(0,0,0,0.85)] text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[16px]">􀥾</p>
      </div>
    </div>
  );
}

function Frame17() {
  return (
    <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]" data-name="Frame">
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
          <Frame18 />
          <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-[rgba(0,0,0,0.85)] text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[16px] overflow-hidden">Macintosh HD</p>
          </div>
          <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-[#bfbfbf] text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px]">Detail</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame20() {
  return (
    <div className="h-[16px] relative shrink-0 w-[18px]" data-name="Frame">
      <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[11px] text-[rgba(0,0,0,0.85)] text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
        <p className="leading-[16px]">􀈑</p>
      </div>
    </div>
  );
}

function Frame19() {
  return (
    <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]" data-name="Frame">
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
          <Frame20 />
          <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-[rgba(0,0,0,0.85)] text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[16px] overflow-hidden">Trash</p>
          </div>
          <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-[#bfbfbf] text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px]">Detail</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Frame() {
  return (
    <div className="content-stretch flex flex-col items-start py-[10px] relative shrink-0 w-full" data-name="Frame">
      <WindowControls />
      <div className="h-[24px] relative rounded-[5px] shrink-0 w-full" data-name="Item">
        <div className="flex flex-row items-center size-full">
          <div className="content-stretch flex items-center px-[10px] relative size-full">
            <Frame1 />
          </div>
        </div>
      </div>
      <div className="h-[24px] relative rounded-[5px] shrink-0 w-full" data-name="Item">
        <div className="flex flex-row items-center size-full">
          <div className="content-stretch flex items-center px-[10px] relative size-full">
            <Frame3 />
          </div>
        </div>
      </div>
      <div className="h-[24px] relative rounded-[5px] shrink-0 w-full" data-name="Item">
        <div className="flex flex-row items-center size-full">
          <div className="content-stretch flex items-center px-[10px] relative size-full">
            <Frame5 />
          </div>
        </div>
      </div>
      <div className="h-[34px] relative shrink-0 w-full" data-name="Section Header">
        <div className="content-stretch flex items-start pb-[5px] pl-[18px] pr-[12px] pt-[15px] relative size-full">
          <p className="flex-[1_0_0] font-['SF_Pro:Bold',sans-serif] font-bold leading-[14px] min-h-px min-w-px relative self-stretch text-[11px] text-[rgba(0,0,0,0.5)]" style={{ fontVariationSettings: "'wdth' 100" }}>
            Favorites
          </p>
          <div className="relative self-stretch shrink-0 w-[24px]" data-name="Disclosure">
            <div className="-translate-x-1/2 -translate-y-1/2 absolute flex flex-col font-['SF_Pro:Bold',sans-serif] font-bold h-[14px] justify-center leading-[0] left-[12px] text-[11px] text-[rgba(0,0,0,0.25)] text-center top-1/2 w-[24px]" style={{ fontVariationSettings: "'wdth' 100" }}>
              <p className="leading-[14px]">􀆈</p>
            </div>
          </div>
        </div>
      </div>
      <div className="h-[24px] relative rounded-[5px] shrink-0 w-full" data-name="Item">
        <div className="flex flex-row items-center size-full">
          <div className="content-stretch flex items-center px-[10px] relative size-full">
            <Frame7 />
          </div>
        </div>
      </div>
      <div className="h-[24px] relative rounded-[5px] shrink-0 w-full" data-name="Item">
        <div className="flex flex-row items-center size-full">
          <div className="content-stretch flex items-center px-[10px] relative size-full">
            <Frame9 />
          </div>
        </div>
      </div>
      <div className="h-[24px] relative rounded-[5px] shrink-0 w-full" data-name="Item">
        <div className="flex flex-row items-center size-full">
          <div className="content-stretch flex items-center px-[10px] relative size-full">
            <Frame11 />
          </div>
        </div>
      </div>
      <div className="h-[34px] relative shrink-0 w-full" data-name="Section Header">
        <div className="content-stretch flex items-start pb-[5px] pl-[18px] pr-[12px] pt-[15px] relative size-full">
          <p className="flex-[1_0_0] font-['SF_Pro:Bold',sans-serif] font-bold leading-[14px] min-h-px min-w-px relative self-stretch text-[11px] text-[rgba(0,0,0,0.5)]" style={{ fontVariationSettings: "'wdth' 100" }}>
            Locations
          </p>
          <p className="font-['SF_Pro:Medium',sans-serif] font-[510] leading-[14px] relative self-stretch shrink-0 text-[11px] text-[rgba(0,0,0,0.5)] w-[31px]" style={{ fontVariationSettings: "'wdth' 100" }}>
            Detail
          </p>
          <div className="relative self-stretch shrink-0 w-[24px]" data-name="Disclosure">
            <div className="-translate-x-1/2 -translate-y-1/2 absolute flex flex-col font-['SF_Pro:Bold',sans-serif] font-bold h-[14px] justify-center leading-[0] left-[12px] text-[11px] text-[rgba(0,0,0,0.25)] text-center top-1/2 w-[24px]" style={{ fontVariationSettings: "'wdth' 100" }}>
              <p className="leading-[14px]">􀆈</p>
            </div>
          </div>
        </div>
      </div>
      <div className="h-[24px] relative rounded-[5px] shrink-0 w-full" data-name="Item">
        <div className="flex flex-row items-center size-full">
          <div className="content-stretch flex items-center px-[10px] relative size-full">
            <Frame13 />
          </div>
        </div>
      </div>
      <div className="h-[24px] relative rounded-[5px] shrink-0 w-full" data-name="Item">
        <div className="flex flex-row items-center size-full">
          <div className="content-stretch flex items-center px-[10px] relative size-full">
            <Frame15 />
          </div>
        </div>
      </div>
      <div className="h-[24px] relative rounded-[5px] shrink-0 w-full" data-name="Item">
        <div className="flex flex-row items-center size-full">
          <div className="content-stretch flex items-center px-[10px] relative size-full">
            <Frame17 />
          </div>
        </div>
      </div>
      <div className="h-[24px] relative rounded-[5px] shrink-0 w-full" data-name="Item">
        <div className="flex flex-row items-center size-full">
          <div className="content-stretch flex items-center px-[10px] relative size-full">
            <Frame19 />
          </div>
        </div>
      </div>
      <div className="h-[34px] relative shrink-0 w-full" data-name="Section Header">
        <div className="content-stretch flex items-start pb-[5px] pl-[18px] pr-[12px] pt-[15px] relative size-full">
          <p className="flex-[1_0_0] font-['SF_Pro:Bold',sans-serif] font-bold leading-[14px] min-h-px min-w-px relative self-stretch text-[11px] text-[rgba(0,0,0,0.5)]" style={{ fontVariationSettings: "'wdth' 100" }}>
            Tags
          </p>
          <p className="font-['SF_Pro:Medium',sans-serif] font-[510] leading-[14px] relative self-stretch shrink-0 text-[11px] text-[rgba(0,0,0,0.5)] w-[31px]" style={{ fontVariationSettings: "'wdth' 100" }}>
            Detail
          </p>
          <div className="relative self-stretch shrink-0 w-[24px]" data-name="Disclosure">
            <div className="-translate-x-1/2 -translate-y-1/2 absolute flex flex-col font-['SF_Pro:Bold',sans-serif] font-bold h-[14px] justify-center leading-[0] left-[12px] text-[11px] text-[rgba(0,0,0,0.25)] text-center top-1/2 w-[24px]" style={{ fontVariationSettings: "'wdth' 100" }}>
              <p className="leading-[14px]">􀆊</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Example() {
  return (
    <div className="content-stretch flex flex-col items-start relative size-full" data-name="Example">
      <FillShadow />
      <GlassEffect />
      <Frame />
    </div>
  );
}