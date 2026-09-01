"use client";

import { useEffect, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";

type ModalPosition = {
  x: number;
  y: number;
};

type DragState = {
  startX: number;
  startY: number;
  originX: number;
  originY: number;
  modal: HTMLElement;
};

const INTERACTIVE_TARGETS = "button, input, select, textarea, a, label, [data-modal-no-drag]";

export function useDraggableModal(isOpen: boolean) {
  const [position, setPosition] = useState<ModalPosition>({ x: 0, y: 0 });
  const dragRef = useRef<DragState | null>(null);

  useEffect(() => {
    if (!isOpen) {
      dragRef.current = null;
      setPosition({ x: 0, y: 0 });
    }
  }, [isOpen]);

  function onPointerDown(event: ReactPointerEvent<HTMLElement>) {
    if (event.button !== 0 || (event.target instanceof Element && event.target.closest(INTERACTIVE_TARGETS))) {
      return;
    }

    const modal = event.currentTarget.parentElement;
    if (!modal) {
      return;
    }

    dragRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: position.x,
      originY: position.y,
      modal,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: ReactPointerEvent<HTMLElement>) {
    const drag = dragRef.current;
    if (!drag) {
      return;
    }

    const horizontalLimit = Math.max(0, (window.innerWidth - drag.modal.offsetWidth) / 2 - 12);
    const verticalLimit = Math.max(0, (window.innerHeight - drag.modal.offsetHeight) / 2 - 12);
    const x = drag.originX + event.clientX - drag.startX;
    const y = drag.originY + event.clientY - drag.startY;

    setPosition({
      x: Math.max(-horizontalLimit, Math.min(horizontalLimit, x)),
      y: Math.max(-verticalLimit, Math.min(verticalLimit, y)),
    });
  }

  function stopDragging(event: ReactPointerEvent<HTMLElement>) {
    dragRef.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return {
    modalStyle: { transform: `translate(${position.x}px, ${position.y}px)` } as CSSProperties,
    dragHandleProps: {
      onPointerDown,
      onPointerMove,
      onPointerUp: stopDragging,
      onPointerCancel: stopDragging,
    },
  };
}