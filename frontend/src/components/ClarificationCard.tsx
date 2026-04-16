import { useState } from "react";
import type { ClarificationOption } from "../types/api";

interface ClarificationCardProps {
  clarificationId: string;
  options: ClarificationOption[];
  onSelect: (id: string, index: number) => void;
  disabled: boolean;
}

export default function ClarificationCard({
  clarificationId,
  options,
  onSelect,
  disabled,
}: ClarificationCardProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const handleSelect = (index: number) => {
    if (disabled || selectedIndex !== null) return;
    setSelectedIndex(index);
    onSelect(clarificationId, index);
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-700">
        I want to make sure I answer the right question. Which of these did you
        mean?
      </p>
      <div className="flex flex-col gap-2">
        {options.map((option, index) => {
          const isSelected = selectedIndex === index;
          const isDimmed = selectedIndex !== null && !isSelected;

          return (
            <button
              key={index}
              onClick={() => handleSelect(index)}
              disabled={disabled || selectedIndex !== null}
              className={`w-full rounded-lg border px-4 py-3 text-left text-sm transition-all ${
                isSelected
                  ? "border-brand bg-brand/5 ring-1 ring-brand"
                  : isDimmed
                    ? "border-gray-100 bg-gray-50 opacity-50"
                    : "border-gray-200 bg-surface-alt hover:border-brand/50 hover:bg-brand/5"
              } ${!disabled && selectedIndex === null ? "cursor-pointer" : "cursor-default"}`}
            >
              <span className="font-medium text-gray-800">{option.label}</span>
              <span className="mt-0.5 block text-xs text-gray-500">
                {option.description}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
