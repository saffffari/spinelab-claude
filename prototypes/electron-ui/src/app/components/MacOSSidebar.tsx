import { ReactNode } from 'react';

interface SidebarItemProps {
  icon: string;
  label: string;
  detail?: string;
  isSelected?: boolean;
  onClick?: () => void;
}

function SidebarItem({ icon, label, detail, isSelected, onClick }: SidebarItemProps) {
  return (
    <div 
      className={`h-[24px] relative rounded-[5px] shrink-0 w-full cursor-pointer ${isSelected ? 'bg-white/10' : 'hover:bg-white/5'}`}
      onClick={onClick}
    >
      <div className="flex flex-row items-center size-full">
        <div className="content-stretch flex items-center px-[10px] relative size-full">
          <div className="flex-[1_0_0] h-full min-h-px min-w-px relative rounded-[8px]">
            <div className="flex flex-row items-center size-full">
              <div className="content-stretch flex gap-[6px] items-center pl-[8px] pr-[10px] py-[4px] relative size-full">
                <div className="h-[16px] relative shrink-0 w-[18px]">
                  <div className="-translate-y-1/2 absolute flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] right-[10px] text-[11px] text-white/80 text-center top-[8px] translate-x-1/2 w-[20px]" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
                    <p className="leading-[16px]">{icon}</p>
                  </div>
                </div>
                <div className="flex flex-[1_0_0] flex-col font-['SF_Pro:Medium',sans-serif] font-[510] h-[16px] justify-center leading-[0] min-h-px min-w-px overflow-hidden relative text-[11px] text-white/80 text-ellipsis whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
                  <p className="leading-[16px] overflow-hidden">{label}</p>
                </div>
                {detail && (
                  <div className="flex flex-col font-['SF_Pro:Medium',sans-serif] font-[510] justify-center leading-[0] relative shrink-0 text-white/40 text-[11px] text-center whitespace-nowrap" style={{ fontVariationSettings: "'wdth' 100" }}>
                    <p className="leading-[14px]">{detail}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface SectionHeaderProps {
  title: string;
  detail?: string;
  isCollapsed?: boolean;
  onToggle?: () => void;
}

function SectionHeader({ title, detail, isCollapsed, onToggle }: SectionHeaderProps) {
  return (
    <div className="h-[34px] relative shrink-0 w-full" onClick={onToggle}>
      <div className="content-stretch flex items-start pb-[5px] pl-[18px] pr-[12px] pt-[15px] relative size-full">
        <p className="flex-[1_0_0] font-['SF_Pro:Bold',sans-serif] font-bold leading-[14px] min-h-px min-w-px relative self-stretch text-[11px] text-white/50" style={{ fontVariationSettings: "'wdth' 100" }}>
          {title}
        </p>
        {detail && (
          <p className="font-['SF_Pro:Medium',sans-serif] font-[510] leading-[14px] relative self-stretch shrink-0 text-[11px] text-white/40 w-[31px]" style={{ fontVariationSettings: "'wdth' 100" }}>
            {detail}
          </p>
        )}
        <div className="relative self-stretch shrink-0 w-[24px]">
          <div className="-translate-x-1/2 -translate-y-1/2 absolute flex flex-col font-['SF_Pro:Bold',sans-serif] font-bold h-[14px] justify-center leading-[0] left-[12px] text-[11px] text-white/30 text-center top-1/2 w-[24px] cursor-pointer" style={{ fontVariationSettings: "'wdth' 100" }}>
            <p className="leading-[14px] transition-transform duration-200" style={{ transform: isCollapsed ? 'rotate(0deg)' : 'rotate(90deg)' }}>􀆈</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function WindowControls() {
  return (
    <div className="h-[32px] relative shrink-0 w-full">
      <div className="absolute content-stretch flex items-center justify-center px-[7px] py-[3px] right-[10px] rounded-[100px] size-[24px] top-[-4px]">
        <div className="flex flex-col font-['SF_Pro:Semibold',sans-serif] font-[590] justify-center leading-[0] relative shrink-0 size-[24px] text-[#1a1a1a] text-[10px] text-center" style={{ fontVariationSettings: "'wdth' 100", fontFeatureSettings: "'ss16'" }}>
          <p className="leading-[12px]">􀏚</p>
        </div>
      </div>
      <div className="absolute content-stretch flex gap-[9px] items-center left-[10px] p-px top-0">
        <div className="bg-[#ff736a] relative rounded-[100px] shrink-0 size-[14px]">
          <div aria-hidden="true" className="absolute border-[0.5px] border-[rgba(0,0,0,0.1)] border-solid inset-0 pointer-events-none rounded-[100px]" />
        </div>
        <div className="bg-[#febc2e] relative rounded-[100px] shrink-0 size-[14px]">
          <div aria-hidden="true" className="absolute border-[0.5px] border-[rgba(0,0,0,0.1)] border-solid inset-0 pointer-events-none rounded-[100px]" />
        </div>
        <div className="bg-[#19c332] relative rounded-[100px] shrink-0 size-[14px]">
          <div aria-hidden="true" className="absolute border-[0.5px] border-[rgba(0,0,0,0.1)] border-solid inset-0 pointer-events-none rounded-[100px]" />
        </div>
      </div>
    </div>
  );
}

interface MacOSSidebarProps {
  children: ReactNode;
  items?: Array<{
    icon: string;
    label: string;
    detail?: string;
    isSelected?: boolean;
    onClick?: () => void;
  }>;
  sections?: Array<{
    title: string;
    detail?: string;
    items: Array<{
      icon: string;
      label: string;
      detail?: string;
      isSelected?: boolean;
      onClick?: () => void;
    }>;
  }>;
}

export function MacOSSidebar({ children, items = [], sections = [] }: MacOSSidebarProps) {
  return (
    <div className="content-stretch flex flex-col items-start relative size-full">
      {/* Fill + Shadow */}
      <div className="absolute inset-0 rounded-[18px] shadow-[0px_8px_40px_0px_rgba(0,0,0,0.12)]">
        <div aria-hidden="true" className="absolute inset-0 pointer-events-none rounded-[18px]">
          <div className="absolute bg-[#262626] inset-0 mix-blend-color-dodge rounded-[18px]" />
          <div className="absolute bg-[rgba(245,245,245,0.67)] inset-0 rounded-[18px]" />
        </div>
      </div>
      
      {/* Glass Effect */}
      <div className="absolute bg-[rgba(0,0,0,0.2)] inset-0 mix-blend-screen rounded-[18px]" />
      
      {/* Content */}
      <div className="content-stretch flex flex-col items-start py-[10px] relative shrink-0 w-full z-10">
        <WindowControls />
        
        {/* Top level items */}
        {items.map((item, index) => (
          <SidebarItem key={index} {...item} />
        ))}
        
        {/* Sections */}
        {sections.map((section, sectionIndex) => (
          <div key={sectionIndex} className="w-full">
            <SectionHeader title={section.title} detail={section.detail} />
            {section.items.map((item, itemIndex) => (
              <SidebarItem key={itemIndex} {...item} />
            ))}
          </div>
        ))}
        
        {children}
      </div>
    </div>
  );
}

export { SidebarItem, SectionHeader };