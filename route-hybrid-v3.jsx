import React, { useState, useMemo, useRef, useEffect, useCallback } from "react";
import {
  Search,
  ChevronDown,
  ChevronRight,
  Filter,
  Download,
  X,
  Check,
  GripVertical,
  Clock,
  MapPin,
  Users,
  AlertTriangle,
  Zap,
  Eye,
  Play,
  MoreHorizontal,
  Plus,
  Maximize2,
  Minimize2,
  Undo2,
  CheckCircle2,
  History,
} from "lucide-react";

// ─── Mock data ────────────────────────────────────────────────────────────
const busesMeta = {
  SBS1001B: { color: "#ef4444", duration: 38, distance: 15.1, capacity: 12 },
  PB1002C: { color: "#f59e0b", duration: 38, distance: 14.7, capacity: 12 },
  PC1003D: { color: "#10b981", duration: 35, distance: 13.3, capacity: 12 },
  PB1004E: { color: "#3b82f6", duration: 20, distance: 7.1, capacity: 12 },
  SBS1005F: { color: "#8b5cf6", duration: 42, distance: 16.8, capacity: 14 },
  PC1006G: { color: "#ec4899", duration: 28, distance: 10.2, capacity: 12 },
};

const initialStudents = [
  { id: "s1", name: "Ariana Tan", grade: "P5", phone: "9123 4561", address: "Sengkang East Way", area: "Sengkang", time: "6:42 AM", bus: "SBS1001B", stop: 1, parent: "Mrs. Tan" },
  { id: "s2", name: "Marcus Lim", grade: "P4", phone: "9123 4562", address: "Anchorvale Crescent", area: "Sengkang", time: "6:45 AM", bus: "SBS1001B", stop: 2, parent: "Mr. Lim" },
  { id: "s3", name: "Sofia Chen", grade: "P6", phone: "9123 4563", address: "Compassvale Drive", area: "Sengkang", time: "6:48 AM", bus: "SBS1001B", stop: 3, parent: "Mrs. Chen" },
  { id: "s4", name: "Daniel Wong", grade: "P3", phone: "9123 4564", address: "Rivervale Walk", area: "Sengkang", time: "6:51 AM", bus: "SBS1001B", stop: 4, parent: "Mr. Wong" },
  { id: "s5", name: "Isabelle Koh", grade: "P5", phone: "9123 4565", address: "Fernvale Lane", area: "Sengkang", time: "6:54 AM", bus: "SBS1001B", stop: 5, parent: "Mrs. Koh" },
  { id: "s6", name: "Ethan Ng", grade: "P4", phone: "9123 4566", address: "Jalan Kayu", area: "Seletar", time: "6:58 AM", bus: "SBS1001B", stop: 6, parent: "Mr. Ng" },
  { id: "s7", name: "Mei Lin Goh", grade: "P2", phone: "9123 4567", address: "Yio Chu Kang Road", area: "Seletar", time: "7:02 AM", bus: "SBS1001B", stop: 7, parent: "Mrs. Goh" },
  { id: "s8", name: "Rajesh Kumar", grade: "P6", phone: "9123 4568", address: "Seletar Road", area: "Seletar", time: "7:05 AM", bus: "SBS1001B", stop: 8, parent: "Mr. Kumar" },
  { id: "s9", name: "Hannah Teo", grade: "P3", phone: "9123 4569", address: "Mimosa Drive", area: "Seletar Hills", time: "7:08 AM", bus: "SBS1001B", stop: 9, parent: "Mrs. Teo" },
  { id: "s10", name: "Liam Tan", grade: "P5", phone: "9123 4570", address: "Mimosa Road", area: "Seletar Hills", time: "7:10 AM", bus: "SBS1001B", stop: 10, parent: "Mr. Tan" },
  { id: "s11", name: "Charlotte Yap", grade: "P4", phone: "9123 4571", address: "Sunrise Place", area: "Seletar Hills", time: "7:13 AM", bus: "SBS1001B", stop: 11, parent: "Mrs. Yap" },
  { id: "s12", name: "Noah Lee", grade: "P1", phone: "9123 4572", address: "Sunrise Walk", area: "Seletar Hills", time: "7:15 AM", bus: "SBS1001B", stop: 12, parent: "Mr. Lee" },

  { id: "s13", name: "Olivia Chua", grade: "P3", phone: "9123 4573", address: "Buangkok Crescent", area: "Buangkok", time: "6:50 AM", bus: "PB1002C", stop: 1, parent: "Mrs. Chua" },
  { id: "s14", name: "William Tay", grade: "P5", phone: "9123 4574", address: "Buangkok Green", area: "Buangkok", time: "6:53 AM", bus: "PB1002C", stop: 2, parent: "Mr. Tay" },
  { id: "s15", name: "Sophia Goh", grade: "P2", phone: "9123 4575", address: "Hougang Avenue 8", area: "Hougang", time: "6:56 AM", bus: "PB1002C", stop: 3, parent: "Mrs. Goh" },
  { id: "s16", name: "James Sim", grade: "P6", phone: "9123 4576", address: "Hougang Avenue 5", area: "Hougang", time: "6:59 AM", bus: "PB1002C", stop: 4, parent: "Mr. Sim" },
  { id: "s17", name: "Amelia Lau", grade: "P4", phone: "9123 4577", address: "Upper Serangoon Road", area: "Hougang", time: "7:02 AM", bus: "PB1002C", stop: 5, parent: "Mrs. Lau" },
  { id: "s18", name: "Benjamin Ho", grade: "P5", phone: "9123 4578", address: "Lorong Lew Lian", area: "Serangoon", time: "7:05 AM", bus: "PB1002C", stop: 6, parent: "Mr. Ho" },
  { id: "s19", name: "Mia Tan", grade: "P3", phone: "9123 4579", address: "Serangoon North Ave 1", area: "Serangoon", time: "7:08 AM", bus: "PB1002C", stop: 7, parent: "Mrs. Tan" },
  { id: "s20", name: "Lucas Lim", grade: "P4", phone: "9123 4580", address: "Chiltern Drive", area: "Serangoon Gdns", time: "7:11 AM", bus: "PB1002C", stop: 8, parent: "Mr. Lim" },
  { id: "s21", name: "Chloe Ong", grade: "P6", phone: "9123 4581", address: "Burghley Drive", area: "Serangoon Gdns", time: "7:14 AM", bus: "PB1002C", stop: 9, parent: "Mrs. Ong" },
  { id: "s22", name: "Henry Tan", grade: "P2", phone: "9123 4582", address: "Berwick Drive", area: "Serangoon Gdns", time: "7:17 AM", bus: "PB1002C", stop: 10, parent: "Mr. Tan" },

  { id: "s24", name: "Aaliyah Pangilinan", grade: "P4", phone: "9123 4584", address: "Luxus Hill Drive", area: "Luxus Hills", time: "7:09 AM", bus: "PC1003D", stop: 1, parent: "Mrs. Pangilinan" },
  { id: "s25", name: "Ezra Pueblo", grade: "P3", phone: "9123 4585", address: "Seletar Green View", area: "Luxus Hills", time: "7:11 AM", bus: "PC1003D", stop: 2, parent: "Mr. Pueblo" },
  { id: "s26", name: "Zirong Wang", grade: "P5", phone: "9123 4586", address: "NIM Crescent", area: "Seletar Hills", time: "7:15 AM", bus: "PC1003D", stop: 3, parent: "Mrs. Wang" },
  { id: "s27", name: "Layla Hassan", grade: "P6", phone: "9123 4587", address: "NIM Drive", area: "Seletar Hills", time: "7:18 AM", bus: "PC1003D", stop: 4, parent: "Mr. Hassan" },
  { id: "s28", name: "Caleb Tan", grade: "P2", phone: "9123 4588", address: "NIM Road", area: "Seletar Hills", time: "7:21 AM", bus: "PC1003D", stop: 5, parent: "Mrs. Tan" },
  { id: "s29", name: "Zoe Ang", grade: "P4", phone: "9123 4589", address: "Greenwich Drive", area: "Seletar Hills", time: "7:24 AM", bus: "PC1003D", stop: 6, parent: "Mr. Ang" },
  { id: "s30", name: "Mason Toh", grade: "P5", phone: "9123 4590", address: "Greenwich View", area: "Seletar Hills", time: "7:27 AM", bus: "PC1003D", stop: 7, parent: "Mrs. Toh" },
  { id: "s31", name: "Eva Lim", grade: "P3", phone: "9123 4591", address: "Greenwich Walk", area: "Seletar Hills", time: "7:30 AM", bus: "PC1003D", stop: 8, parent: "Mr. Lim" },

  { id: "s35", name: "Aaliyah Jacelynn", grade: "P3", phone: "9123 4595", address: "Luxus Hill Drive", area: "Luxus Hills", time: "7:09 AM", bus: "PB1004E", stop: 1, parent: "Mrs. Jacelynn" },
  { id: "s36", name: "Ezra Pueblo Jr", grade: "P5", phone: "9123 4596", address: "Seletar Green View", area: "Luxus Hills", time: "7:11 AM", bus: "PB1004E", stop: 2, parent: "Mr. Pueblo" },
  { id: "s37", name: "Zirong Wang", grade: "P4", phone: "9123 4597", address: "NIM Crescent", area: "Seletar Hills", time: "7:15 AM", bus: "PB1004E", stop: 3, parent: "Mrs. Wang" },
  { id: "s38", name: "Maya Subramaniam", grade: "P6", phone: "9123 4598", address: "NIM Green", area: "Seletar Hills", time: "7:17 AM", bus: "PB1004E", stop: 4, parent: "Mr. Subramaniam" },
  { id: "s39", name: "Theodore Ng", grade: "P2", phone: "9123 4599", address: "NIM Place", area: "Seletar Hills", time: "7:19 AM", bus: "PB1004E", stop: 5, parent: "Mrs. Ng" },
  { id: "s40", name: "Penelope Quek", grade: "P5", phone: "9123 4600", address: "Greenwich Avenue", area: "Seletar Hills", time: "7:22 AM", bus: "PB1004E", stop: 6, parent: "Mr. Quek" },
  { id: "s41", name: "Sebastian Lai", grade: "P3", phone: "9123 4601", address: "Greenwich Crescent", area: "Seletar Hills", time: "7:24 AM", bus: "PB1004E", stop: 7, parent: "Mrs. Lai" },
  { id: "s42", name: "Violet Tham", grade: "P4", phone: "9123 4602", address: "Mimosa Crescent", area: "Seletar Hills", time: "7:26 AM", bus: "PB1004E", stop: 8, parent: "Mr. Tham" },
  { id: "s43", name: "Felix Loh", grade: "P5", phone: "9123 4603", address: "Mimosa Avenue", area: "Seletar Hills", time: "7:28 AM", bus: "PB1004E", stop: 9, parent: "Mrs. Loh" },

  { id: "s44", name: "Eliana Foo", grade: "P4", phone: "9123 4604", address: "Yishun Avenue 2", area: "Yishun", time: "6:35 AM", bus: "SBS1005F", stop: 1, parent: "Mrs. Foo" },
  { id: "s45", name: "Maxwell Tan", grade: "P6", phone: "9123 4605", address: "Yishun Street 11", area: "Yishun", time: "6:38 AM", bus: "SBS1005F", stop: 2, parent: "Mr. Tan" },
  { id: "s46", name: "Aurora Lim", grade: "P3", phone: "9123 4606", address: "Khatib Vale", area: "Khatib", time: "6:42 AM", bus: "SBS1005F", stop: 3, parent: "Mrs. Lim" },
  { id: "s47", name: "Hudson Wee", grade: "P5", phone: "9123 4607", address: "Khatib Bongsu", area: "Khatib", time: "6:45 AM", bus: "SBS1005F", stop: 4, parent: "Mr. Wee" },
  { id: "s48", name: "Stella Ng", grade: "P2", phone: "9123 4608", address: "Sembawang Drive", area: "Sembawang", time: "6:50 AM", bus: "SBS1005F", stop: 5, parent: "Mrs. Ng" },

  { id: "s49", name: "Iris Chong", grade: "P3", phone: "9123 4609", address: "Punggol Walk", area: "Punggol", time: "—", bus: null, stop: null, parent: "Mrs. Chong" },
  { id: "s50", name: "Ryan Sng", grade: "P5", phone: "9123 4610", address: "Punggol Field", area: "Punggol", time: "—", bus: null, stop: null, parent: "Mr. Sng" },
];

const gradeColors = {
  P1: "#fbbf24", P2: "#fb923c", P3: "#f87171",
  P4: "#a78bfa", P5: "#60a5fa", P6: "#34d399",
};

const ROW_HEIGHT = 38;
const DRAG_THRESHOLD = 5; // pixels before drag starts

export default function HybridRouteManager() {
  const [committedStudents, setCommittedStudents] = useState(initialStudents);
  const [students, setStudents] = useState(initialStudents);
  const [pendingChanges, setPendingChanges] = useState({});

  const [selected, setSelected] = useState(new Set());
  const [search, setSearch] = useState("");
  const [busFilter, setBusFilter] = useState(new Set());
  const [gradeFilter, setGradeFilter] = useState(new Set());
  const [collapsedBuses, setCollapsedBuses] = useState(new Set());
  const [showHistory, setShowHistory] = useState(false);

  // ─── Pointer-based drag state ──────────────────────────────────────────
  const [drag, setDrag] = useState(null);
  // drag = { ids, sourceBus, mouseX, mouseY, targetBus, targetIndex } | null

  const dragStartRef = useRef(null); // {x, y, studentId, sourceBus} - tracks initial mousedown
  const laneRefs = useRef({}); // { busId: HTMLElement }
  const rowRefs = useRef({}); // { studentId: HTMLElement }

  const allBusIds = ["__unassigned", ...Object.keys(busesMeta)];

  const filtered = useMemo(() => {
    let list = students;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.address.toLowerCase().includes(q) ||
          s.area.toLowerCase().includes(q) ||
          (s.parent || "").toLowerCase().includes(q)
      );
    }
    if (busFilter.size) list = list.filter((s) => busFilter.has(s.bus || "__unassigned"));
    if (gradeFilter.size) list = list.filter((s) => gradeFilter.has(s.grade));
    return list;
  }, [students, search, busFilter, gradeFilter]);

  const groupedByBus = useMemo(() => {
    const map = new Map();
    allBusIds.forEach((id) => map.set(id, []));
    filtered.forEach((s) => {
      const k = s.bus || "__unassigned";
      if (map.has(k)) map.get(k).push(s);
    });
    map.forEach((items) => items.sort((a, b) => (a.stop ?? 999) - (b.stop ?? 999)));
    return map;
  }, [filtered, students]);

  // ─── Selection ─────────────────────────────────────────────────────────
  const toggleRow = (id) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };
  const toggleBusSelection = (busId) => {
    const items = groupedByBus.get(busId) || [];
    const allSel = items.length > 0 && items.every((s) => selected.has(s.id));
    const next = new Set(selected);
    items.forEach((s) => (allSel ? next.delete(s.id) : next.add(s.id)));
    setSelected(next);
  };
  const toggleCollapse = (busId) => {
    const next = new Set(collapsedBuses);
    next.has(busId) ? next.delete(busId) : next.add(busId);
    setCollapsedBuses(next);
  };

  // ─── Pointer events for drag ───────────────────────────────────────────
  const handlePointerDown = (e, studentId, sourceBus) => {
    // Only start drag from grip handle or drag-trigger area
    if (e.button !== 0) return; // left click only
    e.preventDefault();
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      studentId,
      sourceBus,
      started: false,
    };
    document.addEventListener("pointermove", handlePointerMove);
    document.addEventListener("pointerup", handlePointerUp);
  };

  const handlePointerMove = useCallback((e) => {
    const start = dragStartRef.current;
    if (!start) return;

    if (!start.started) {
      const dx = e.clientX - start.x;
      const dy = e.clientY - start.y;
      if (Math.sqrt(dx * dx + dy * dy) < DRAG_THRESHOLD) return;

      // Threshold passed → start drag
      start.started = true;
      const ids =
        selected.has(start.studentId) && selected.size > 1
          ? Array.from(selected)
          : [start.studentId];
      setDrag({
        ids,
        sourceBus: start.sourceBus,
        mouseX: e.clientX,
        mouseY: e.clientY,
        targetBus: null,
        targetIndex: null,
      });
      document.body.style.userSelect = "none";
      document.body.style.cursor = "grabbing";
    } else {
      // Update position + detect drop target
      const target = detectDropTarget(e.clientX, e.clientY);
      setDrag((prev) =>
        prev
          ? {
              ...prev,
              mouseX: e.clientX,
              mouseY: e.clientY,
              targetBus: target?.busId ?? null,
              targetIndex: target?.index ?? null,
            }
          : null
      );
    }
  }, [selected]);

  const detectDropTarget = (x, y) => {
    // Find the element under the cursor
    const el = document.elementFromPoint(x, y);
    if (!el) return null;
    const laneEl = el.closest("[data-bus-lane]");
    if (!laneEl) return null;
    const busId = laneEl.getAttribute("data-bus-lane");

    // Find which row index we're over
    const rowEls = laneEl.querySelectorAll("[data-row-index]");
    let targetIndex = rowEls.length; // default: end
    for (let i = 0; i < rowEls.length; i++) {
      const rect = rowEls[i].getBoundingClientRect();
      if (y < rect.top + rect.height / 2) {
        targetIndex = i;
        break;
      }
    }
    return { busId, index: targetIndex };
  };

  const handlePointerUp = useCallback(() => {
    document.removeEventListener("pointermove", handlePointerMove);
    document.removeEventListener("pointerup", handlePointerUp);
    document.body.style.userSelect = "";
    document.body.style.cursor = "";

    const start = dragStartRef.current;
    dragStartRef.current = null;

    if (!start || !start.started) {
      // Was just a click, not a drag → clear drag state
      setDrag(null);
      return;
    }

    // Apply drop
    setDrag((current) => {
      if (!current) return null;
      const { ids, sourceBus, targetBus } = current;

      if (targetBus === null) return null; // dropped outside any lane

      // Same bus, no real movement → ignore
      if (targetBus === sourceBus && ids.length === 1) {
        // Only ignore if dropping at exact same position; for simplicity we ignore same-bus drops entirely here
        return null;
      }

      const realTarget = targetBus === "__unassigned" ? null : targetBus;
      // Apply tentatively + record pending
      setStudents((prev) =>
        prev.map((s) => (ids.includes(s.id) ? { ...s, bus: realTarget } : s))
      );
      setPendingChanges((prev) => {
        const next = { ...prev };
        ids.forEach((id) => {
          const original = committedStudents.find((s) => s.id === id);
          const originalBus = original?.bus || null;
          if (originalBus === realTarget) {
            delete next[id];
          } else {
            next[id] = { from: originalBus, to: realTarget };
          }
        });
        return next;
      });
      setSelected(new Set());
      return null;
    });
  }, [committedStudents, handlePointerMove]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      document.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("pointerup", handlePointerUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
  }, [handlePointerMove, handlePointerUp]);

  // ─── Confirmation flow ─────────────────────────────────────────────────
  const pendingCount = Object.keys(pendingChanges).length;

  const confirmAll = () => {
    setCommittedStudents(students);
    setPendingChanges({});
  };

  const discardAll = () => {
    setStudents(committedStudents);
    setPendingChanges({});
  };

  const undoChange = (studentId) => {
    const change = pendingChanges[studentId];
    if (!change) return;
    setStudents((prev) =>
      prev.map((s) => (s.id === studentId ? { ...s, bus: change.from } : s))
    );
    setPendingChanges((prev) => {
      const next = { ...prev };
      delete next[studentId];
      return next;
    });
  };

  const bulkAssign = (targetBusId) => {
    const realTarget = targetBusId === "__unassigned" ? null : targetBusId;
    const idsToMove = Array.from(selected);
    setStudents((prev) =>
      prev.map((s) => (selected.has(s.id) ? { ...s, bus: realTarget } : s))
    );
    setPendingChanges((prev) => {
      const next = { ...prev };
      idsToMove.forEach((id) => {
        const original = committedStudents.find((s) => s.id === id);
        const originalBus = original?.bus || null;
        if (originalBus === realTarget) {
          delete next[id];
        } else {
          next[id] = { from: originalBus, to: realTarget };
        }
      });
      return next;
    });
    setSelected(new Set());
  };

  const toggleSetItem = (set, value, setter) => {
    const next = new Set(set);
    next.has(value) ? next.delete(value) : next.add(value);
    setter(next);
  };

  const isPending = (id) => pendingChanges[id] !== undefined;
  const draggedStudentObjs = drag ? drag.ids.map((id) => students.find((s) => s.id === id)).filter(Boolean) : [];
  const isDragging = drag !== null;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 antialiased">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
        * { font-family: 'Inter Tight', system-ui, sans-serif; }
        .mono { font-family: 'JetBrains Mono', monospace; font-feature-settings: 'tnum'; }
        .scrollbar-thin::-webkit-scrollbar { width: 10px; height: 10px; }
        .scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
        .scrollbar-thin::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 5px; border: 2px solid transparent; background-clip: padding-box; }
        .scrollbar-thin::-webkit-scrollbar-thumb:hover { background: #94a3b8; background-clip: padding-box; border: 2px solid transparent; }
        @keyframes slideUp { from { transform: translate(-50%, 100%); opacity: 0; } to { transform: translate(-50%, 0); opacity: 1; } }
        .slide-up { animation: slideUp 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
        @keyframes slideDown { from { transform: translateY(-100%); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
        .slide-down { animation: slideDown 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        .fade-in { animation: fadeIn 0.12s ease-out; }
        @keyframes pulseGlow { 0%, 100% { box-shadow: inset 0 0 0 2px rgb(59 130 246 / 0.5); } 50% { box-shadow: inset 0 0 0 2px rgb(59 130 246 / 0.9); } }
        .drop-zone-active { animation: pulseGlow 1.4s ease-in-out infinite; background: linear-gradient(180deg, rgba(59,130,246,0.04), rgba(59,130,246,0.10)); }
        .row-shift { transition: transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1); }
        @keyframes wiggle { 0%, 100% { transform: rotate(-2deg); } 50% { transform: rotate(-1.4deg); } }
        .floating-ghost { animation: wiggle 0.5s ease-in-out infinite; }
        @keyframes pendingPulse { 0%, 100% { background: rgba(59, 130, 246, 0.06); } 50% { background: rgba(59, 130, 246, 0.12); } }
        .pending-row { animation: pendingPulse 2.5s ease-in-out infinite; border-left: 3px solid #3b82f6 !important; }
        .drop-indicator-line { background: linear-gradient(90deg, transparent, #3b82f6 20%, #3b82f6 80%, transparent); }
        @keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
        .pending-bar-shimmer { background: linear-gradient(90deg, #1e40af 0%, #3b82f6 50%, #1e40af 100%); background-size: 200% 100%; animation: shimmer 3s linear infinite; }
        .drag-handle { touch-action: none; }
      `}</style>

      {/* Pending changes banner */}
      {pendingCount > 0 && (
        <div className="sticky top-0 z-40 slide-down pending-bar-shimmer text-white">
          <div className="px-6 h-11 flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-amber-300 animate-pulse" />
              <span className="text-sm font-semibold">
                {pendingCount} pending change{pendingCount > 1 ? "s" : ""}
              </span>
              <span className="text-xs text-blue-100">— not saved yet</span>
            </div>

            <button
              onClick={() => setShowHistory(!showHistory)}
              className="ml-2 h-7 px-2.5 text-xs font-medium text-white/90 hover:bg-white/10 rounded-md transition-colors flex items-center gap-1.5"
            >
              <History size={12} />
              {showHistory ? "Hide" : "Review"} changes
            </button>

            <div className="ml-auto flex items-center gap-1.5">
              <button
                onClick={discardAll}
                className="h-7 px-3 text-xs font-medium text-white/90 hover:bg-white/15 rounded-md transition-colors flex items-center gap-1.5"
              >
                <X size={12} /> Discard
              </button>
              <button
                onClick={confirmAll}
                className="h-7 px-3.5 text-xs font-bold text-blue-700 bg-white hover:bg-blue-50 rounded-md transition-colors flex items-center gap-1.5 shadow-sm"
              >
                <CheckCircle2 size={12} /> Confirm {pendingCount} change{pendingCount > 1 ? "s" : ""}
              </button>
            </div>
          </div>

          {showHistory && (
            <div className="bg-blue-950/30 border-t border-white/10 px-6 py-2 max-h-48 overflow-auto scrollbar-thin">
              <div className="space-y-1">
                {Object.entries(pendingChanges).map(([id, change]) => {
                  const student = students.find((s) => s.id === id);
                  if (!student) return null;
                  return (
                    <div
                      key={id}
                      className="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-white/10 group"
                    >
                      <span className="font-medium text-white w-40 truncate">{student.name}</span>
                      <span className="mono text-blue-200">{change.from || "Unassigned"}</span>
                      <ChevronRight size={11} className="text-blue-300" />
                      <span className="mono font-semibold text-white">{change.to || "Unassigned"}</span>
                      <button
                        onClick={() => undoChange(id)}
                        className="ml-auto h-6 px-2 text-[10px] font-medium text-blue-100 hover:bg-white/15 rounded opacity-0 group-hover:opacity-100 transition-all flex items-center gap-1"
                      >
                        <Undo2 size={10} /> Undo
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Header bar */}
      <div className="bg-white border-b border-slate-200 sticky z-30" style={{ top: pendingCount > 0 ? (showHistory ? "auto" : 44) : 0 }}>
        <div className="px-6 h-12 flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400">RouteOptimise</span>
            <ChevronRight size={11} className="text-slate-300" />
            <span className="text-slate-400">Results</span>
            <ChevronRight size={11} className="text-slate-300" />
            <span className="font-semibold text-slate-800">Manage routes</span>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <button className="h-7 px-2.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded-md transition-colors flex items-center gap-1.5">
              <Download size={13} /> Export
            </button>
            <button className="h-7 px-2.5 text-xs font-medium text-white bg-slate-900 hover:bg-slate-800 rounded-md transition-colors flex items-center gap-1.5">
              <Zap size={13} /> Fetch real routes
            </button>
          </div>
        </div>

        <div className="px-6 h-11 flex items-center gap-1.5 border-t border-slate-100">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search students, addresses, parents…"
              className="h-7 w-72 pl-8 pr-2 text-sm bg-slate-50 border border-slate-200 rounded-md focus:bg-white focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-100 transition-all placeholder:text-slate-400"
            />
          </div>

          <div className="h-5 w-px bg-slate-200 mx-1" />

          <FilterDropdown
            label="Bus"
            count={busFilter.size}
            options={allBusIds.map((id) => ({
              value: id,
              label: id === "__unassigned" ? "Unassigned" : id,
              color: id === "__unassigned" ? "#94a3b8" : busesMeta[id].color,
            }))}
            selected={busFilter}
            onToggle={(v) => toggleSetItem(busFilter, v, setBusFilter)}
            onClear={() => setBusFilter(new Set())}
          />

          <FilterDropdown
            label="Grade"
            count={gradeFilter.size}
            options={["P1", "P2", "P3", "P4", "P5", "P6"].map((g) => ({
              value: g, label: g, color: gradeColors[g],
            }))}
            selected={gradeFilter}
            onToggle={(v) => toggleSetItem(gradeFilter, v, setGradeFilter)}
            onClear={() => setGradeFilter(new Set())}
          />

          <div className="h-5 w-px bg-slate-200 mx-1" />

          <button
            onClick={() => setCollapsedBuses(new Set(allBusIds))}
            className="h-7 px-2 text-xs font-medium text-slate-500 hover:bg-slate-100 rounded-md transition-colors flex items-center gap-1"
          >
            <Minimize2 size={11} /> Collapse all
          </button>
          <button
            onClick={() => setCollapsedBuses(new Set())}
            className="h-7 px-2 text-xs font-medium text-slate-500 hover:bg-slate-100 rounded-md transition-colors flex items-center gap-1"
          >
            <Maximize2 size={11} /> Expand all
          </button>

          <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
            <span>
              <span className="mono font-semibold text-slate-700">{filtered.length}</span> of{" "}
              <span className="mono">{students.length}</span>
            </span>
            {pendingCount > 0 && (
              <>
                <span className="text-slate-300">·</span>
                <span className="text-blue-600 font-medium mono">{pendingCount} pending</span>
              </>
            )}
            <span className="text-slate-300">·</span>
            <span className="flex items-center gap-1 text-slate-500">
              <GripVertical size={10} className="text-slate-400" /> Drag the grip handle to move
            </span>
          </div>
        </div>
      </div>

      {/* Main scroll area */}
      <div
        className="overflow-auto scrollbar-thin"
        style={{ height: `calc(100vh - ${pendingCount > 0 ? 140 : 96}px)` }}
      >
        <div className="min-w-[1200px]">
          {/* Sticky column header */}
          <div className="sticky top-0 z-20 bg-slate-100/90 backdrop-blur-sm border-b border-slate-200">
            <div
              className="grid items-center h-9 px-6 text-[10px] font-bold text-slate-500 uppercase tracking-wider"
              style={{ gridTemplateColumns: "32px 28px 50px 1fr 70px 110px 1.4fr 130px 130px 100px 40px" }}
            >
              <div></div>
              <div></div>
              <div className="text-center">Stop</div>
              <div>Student</div>
              <div className="text-center">Grade</div>
              <div>Phone</div>
              <div>Address</div>
              <div>Area</div>
              <div>Parent</div>
              <div className="text-right">Pickup</div>
              <div></div>
            </div>
          </div>

          {/* Bus lanes */}
          {allBusIds.map((busId) => {
            const items = groupedByBus.get(busId) || [];
            const isUnassigned = busId === "__unassigned";
            const meta = isUnassigned ? null : busesMeta[busId];
            const isCollapsed = collapsedBuses.has(busId);
            const isDropTarget = drag?.targetBus === busId;
            const allItemsSelected = items.length > 0 && items.every((s) => selected.has(s.id));
            const someSelected = items.some((s) => selected.has(s.id));
            const capacity = meta?.capacity || 0;
            const load = students.filter((s) => s.bus === (isUnassigned ? null : busId)).length;
            const isFull = !isUnassigned && load >= capacity;
            const isOver = !isUnassigned && load > capacity;
            const wouldReceive = isDropTarget && drag.sourceBus !== busId ? drag.ids.length : 0;
            const projectedLoad = load + wouldReceive;
            // Hide rows being dragged from source
            const visibleItems = items.filter(
              (s) => !(drag && drag.ids.includes(s.id) && drag.sourceBus === busId)
            );

            return (
              <div
                key={busId}
                data-bus-lane={busId}
                className={`relative border-b-2 border-slate-200 transition-all ${
                  isDropTarget ? "drop-zone-active" : ""
                }`}
              >
                {/* Lane header */}
                <div
                  className={`flex items-center h-11 px-6 sticky z-10 backdrop-blur-sm transition-colors ${
                    isUnassigned
                      ? "bg-amber-50/80 border-l-4 border-amber-400"
                      : "bg-white/95"
                  }`}
                  style={{ top: 36 }}
                >
                  {!isUnassigned && (
                    <div className="absolute left-0 top-0 bottom-0 w-1" style={{ background: meta.color }} />
                  )}

                  <button
                    onClick={() => toggleBusSelection(busId)}
                    className={`w-3.5 h-3.5 rounded-[3px] border mr-3 flex items-center justify-center transition-all ${
                      allItemsSelected
                        ? "bg-slate-900 border-slate-900"
                        : someSelected
                        ? "bg-slate-200 border-slate-400"
                        : "border-slate-300 hover:border-slate-500"
                    }`}
                  >
                    {allItemsSelected && <Check size={9} className="text-white" strokeWidth={3.5} />}
                    {someSelected && !allItemsSelected && <div className="w-1.5 h-0.5 bg-slate-600 rounded" />}
                  </button>

                  <button
                    onClick={() => toggleCollapse(busId)}
                    className="w-5 h-5 mr-2 flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors"
                  >
                    <ChevronDown size={14} className={`transition-transform ${isCollapsed ? "-rotate-90" : ""}`} />
                  </button>

                  {!isUnassigned ? (
                    <>
                      <div
                        className="w-2 h-2 rounded-full mr-2.5 ring-2 ring-offset-1"
                        style={{ background: meta.color, "--tw-ring-color": meta.color + "30" }}
                      />
                      <span className="font-bold text-sm mono tracking-tight text-slate-900">{busId}</span>
                      <div className="flex items-center gap-3 ml-4 text-xs">
                        <CapacityIndicator
                          load={load}
                          projectedLoad={projectedLoad}
                          capacity={capacity}
                          color={meta.color}
                          isReceiving={isDropTarget && drag.sourceBus !== busId}
                        />
                        <span className="flex items-center gap-1 text-slate-600">
                          <Clock size={11} className="text-slate-400" />
                          <span className="mono">{meta.duration}</span>
                          <span className="text-slate-400">min</span>
                        </span>
                        <span className="flex items-center gap-1 text-slate-600">
                          <MapPin size={11} className="text-slate-400" />
                          <span className="mono">{meta.distance}</span>
                          <span className="text-slate-400">km</span>
                        </span>
                        {isOver && (
                          <span className="flex items-center gap-1 px-1.5 py-0.5 bg-rose-50 text-rose-600 rounded text-[10px] font-semibold">
                            <AlertTriangle size={10} /> Over capacity
                          </span>
                        )}
                        {isFull && !isOver && (
                          <span className="flex items-center gap-1 px-1.5 py-0.5 bg-amber-50 text-amber-700 rounded text-[10px] font-semibold">
                            Full
                          </span>
                        )}
                      </div>
                    </>
                  ) : (
                    <>
                      <AlertTriangle size={13} className="text-amber-600 mr-2" />
                      <span className="font-bold text-sm text-amber-900">Unassigned students</span>
                      <span className="ml-3 mono text-xs text-amber-700">{load}</span>
                      <span className="ml-2 text-xs text-amber-700/80">need to be assigned to a bus</span>
                    </>
                  )}

                  <div className="ml-auto flex items-center gap-1">
                    {!isUnassigned && (
                      <>
                        <IconButton><Eye size={13} /></IconButton>
                        <IconButton><Play size={13} className="text-emerald-600" /></IconButton>
                        <IconButton><MoreHorizontal size={13} /></IconButton>
                      </>
                    )}
                  </div>
                </div>

                {/* Rows */}
                {!isCollapsed && (
                  <div>
                    {visibleItems.length === 0 && (
                      <div
                        data-row-index="0"
                        className="h-16 mx-6 my-2 border-2 border-dashed border-slate-200 rounded-lg flex items-center justify-center text-xs text-slate-400 transition-colors"
                        style={{
                          borderColor: isDropTarget ? "#3b82f6" : undefined,
                          background: isDropTarget ? "rgba(59,130,246,0.05)" : undefined,
                        }}
                      >
                        {isDropTarget && drag.ids.length > 0 ? (
                          <span className="text-blue-600 font-medium flex items-center gap-1.5">
                            <Plus size={12} /> Release to assign {drag.ids.length} student
                            {drag.ids.length > 1 ? "s" : ""}
                          </span>
                        ) : (
                          "Drop students here to assign"
                        )}
                      </div>
                    )}

                    {visibleItems.map((s, idx) => {
                      const isSelected = selected.has(s.id);
                      const pending = isPending(s.id);
                      const change = pendingChanges[s.id];
                      const shouldShift =
                        isDropTarget &&
                        drag &&
                        drag.targetIndex !== null &&
                        idx >= drag.targetIndex;

                      return (
                        <React.Fragment key={s.id}>
                          {/* Drop indicator above this row */}
                          {isDropTarget && drag.targetIndex === idx && (
                            <div className="h-1 mx-6 my-0 drop-indicator-line rounded-full fade-in" />
                          )}

                          <div
                            data-row-index={idx}
                            ref={(el) => { if (el) rowRefs.current[s.id] = el; }}
                            className={`group border-b border-slate-100 row-shift ${
                              isSelected
                                ? "bg-blue-50/60 hover:bg-blue-50"
                                : pending
                                ? "pending-row"
                                : "bg-white hover:bg-slate-50"
                            }`}
                            style={{
                              display: "grid",
                              gridTemplateColumns: "32px 28px 50px 1fr 70px 110px 1.4fr 130px 130px 100px 40px",
                              alignItems: "center",
                              height: ROW_HEIGHT,
                              transform: shouldShift ? `translateY(${ROW_HEIGHT * (drag?.ids.length || 0)}px)` : "translateY(0)",
                            }}
                          >
                            <div className="pl-6 pr-1">
                              <button
                                onClick={() => toggleRow(s.id)}
                                className={`w-3.5 h-3.5 rounded-[3px] border flex items-center justify-center transition-all ${
                                  isSelected
                                    ? "bg-slate-900 border-slate-900"
                                    : "border-slate-300 hover:border-slate-500 opacity-0 group-hover:opacity-100"
                                } ${isSelected ? "!opacity-100" : ""}`}
                              >
                                {isSelected && <Check size={9} className="text-white" strokeWidth={3.5} />}
                              </button>
                            </div>
                            <div className="px-0">
                              <div
                                onPointerDown={(e) => handlePointerDown(e, s.id, busId)}
                                className="drag-handle w-6 h-6 flex items-center justify-center text-slate-300 group-hover:text-slate-600 hover:!text-slate-900 hover:bg-slate-100 rounded transition-colors cursor-grab active:cursor-grabbing"
                                title="Drag to reassign"
                              >
                                <GripVertical size={14} />
                              </div>
                            </div>
                            <div className="text-center text-xs mono text-slate-400">{s.stop ?? "—"}</div>
                            <div className="pr-2 min-w-0">
                              <div className="flex items-center gap-2 min-w-0">
                                <div
                                  className="w-5 h-5 shrink-0 rounded-full flex items-center justify-center text-[9px] font-bold text-white"
                                  style={{
                                    background: s.bus
                                      ? `linear-gradient(135deg, ${busesMeta[s.bus].color}, ${busesMeta[s.bus].color}cc)`
                                      : "#94a3b8",
                                  }}
                                >
                                  {s.name.split(" ").map((n) => n[0]).slice(0, 2).join("")}
                                </div>
                                <span className="text-sm font-medium text-slate-800 truncate">{s.name}</span>
                                {pending && (
                                  <span
                                    className="shrink-0 inline-flex items-center gap-1 px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded text-[9px] font-bold uppercase tracking-wider"
                                    title={`Was on ${change.from || "Unassigned"}`}
                                  >
                                    <span className="w-1 h-1 rounded-full bg-blue-600 animate-pulse" />
                                    Pending
                                  </span>
                                )}
                              </div>
                            </div>
                            <div className="text-center">
                              <span
                                className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-bold rounded mono"
                                style={{ background: gradeColors[s.grade] + "20", color: gradeColors[s.grade] }}
                              >
                                {s.grade}
                              </span>
                            </div>
                            <div className="text-xs mono text-slate-500 truncate pr-2">{s.phone}</div>
                            <div className="text-xs text-slate-600 truncate pr-2 flex items-center gap-1">
                              <MapPin size={10} className="text-slate-300 shrink-0" />
                              <span className="truncate">{s.address}</span>
                            </div>
                            <div className="text-xs text-slate-500 truncate pr-2">{s.area}</div>
                            <div className="text-xs text-slate-500 truncate pr-2">{s.parent}</div>
                            <div className="text-xs mono text-slate-600 text-right pr-3">{s.time}</div>
                            <div className="text-center">
                              {pending ? (
                                <button
                                  onClick={() => undoChange(s.id)}
                                  className="w-6 h-6 flex items-center justify-center text-blue-600 hover:bg-blue-100 rounded transition-all"
                                  title="Undo this change"
                                >
                                  <Undo2 size={11} />
                                </button>
                              ) : (
                                <button className="w-5 h-5 flex items-center justify-center text-slate-300 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-all rounded">
                                  <X size={12} />
                                </button>
                              )}
                            </div>
                          </div>
                        </React.Fragment>
                      );
                    })}

                    {/* Drop indicator at the bottom */}
                    {isDropTarget && drag.targetIndex === visibleItems.length && visibleItems.length > 0 && (
                      <div className="h-1 mx-6 drop-indicator-line rounded-full fade-in" />
                    )}

                    {!isUnassigned && visibleItems.length > 0 && (
                      <div className="px-6 h-8 flex items-center">
                        <button className="text-[11px] text-slate-400 hover:text-slate-700 flex items-center gap-1 transition-colors">
                          <Plus size={11} /> Add student to {busId}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Floating drag ghost */}
      {isDragging && draggedStudentObjs.length > 0 && (
        <div
          className="fixed pointer-events-none z-[100] floating-ghost"
          style={{
            left: drag.mouseX + 14,
            top: drag.mouseY + 10,
          }}
        >
          <div className="bg-white rounded-lg shadow-2xl shadow-slate-900/30 border border-slate-200 overflow-hidden min-w-[280px] max-w-[340px]">
            {draggedStudentObjs.slice(0, 3).map((s, i) => (
              <div
                key={s.id}
                className="flex items-center gap-2 px-3 py-2 border-b border-slate-100 last:border-b-0"
                style={{ marginTop: i === 0 ? 0 : -2, opacity: 1 - i * 0.15 }}
              >
                <div
                  className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold text-white shrink-0"
                  style={{
                    background: s.bus
                      ? `linear-gradient(135deg, ${busesMeta[s.bus].color}, ${busesMeta[s.bus].color}cc)`
                      : "#94a3b8",
                  }}
                >
                  {s.name.split(" ").map((n) => n[0]).slice(0, 2).join("")}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-slate-900 truncate">{s.name}</div>
                  <div className="text-[10px] text-slate-500 mono truncate">{s.address}</div>
                </div>
                <span
                  className="inline-flex items-center px-1.5 py-0.5 text-[9px] font-bold rounded mono shrink-0"
                  style={{ background: gradeColors[s.grade] + "20", color: gradeColors[s.grade] }}
                >
                  {s.grade}
                </span>
              </div>
            ))}
            {draggedStudentObjs.length > 3 && (
              <div className="bg-slate-900 text-white text-[10px] font-bold px-3 py-1.5 text-center">
                + {draggedStudentObjs.length - 3} more student{draggedStudentObjs.length - 3 > 1 ? "s" : ""}
              </div>
            )}
          </div>
          {draggedStudentObjs.length > 1 && (
            <div className="absolute -top-2 -right-2 w-6 h-6 bg-blue-600 text-white text-[10px] font-bold rounded-full flex items-center justify-center shadow-lg ring-2 ring-white">
              {draggedStudentObjs.length}
            </div>
          )}
        </div>
      )}

      {/* Bulk action bar */}
      {selected.size > 0 && !isDragging && (
        <div className="fixed bottom-5 left-1/2 -translate-x-1/2 slide-up z-50">
          <div className="bg-slate-900 text-white rounded-lg shadow-2xl shadow-slate-900/40 flex items-center gap-1 p-1.5 pr-3">
            <div className="flex items-center gap-2 px-3 py-1 bg-white/10 rounded-md">
              <span className="text-sm font-semibold mono">{selected.size}</span>
              <span className="text-sm text-slate-300">selected</span>
            </div>
            <div className="h-5 w-px bg-white/15 mx-1" />
            <span className="text-xs text-slate-400 px-2">Move to:</span>
            <div className="flex items-center gap-0.5 max-w-md overflow-x-auto scrollbar-thin">
              {Object.keys(busesMeta).map((id) => {
                const load = students.filter((s) => s.bus === id).length;
                const cap = busesMeta[id].capacity;
                const full = load >= cap;
                return (
                  <button
                    key={id}
                    onClick={() => !full && bulkAssign(id)}
                    disabled={full}
                    className="h-7 px-2 text-xs font-medium rounded-md hover:bg-white/10 transition-colors flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
                  >
                    <span className="w-1.5 h-1.5 rounded-full" style={{ background: busesMeta[id].color }} />
                    <span className="mono">{id}</span>
                    <span className="text-[10px] text-slate-400 mono">{load}/{cap}</span>
                  </button>
                );
              })}
            </div>
            <div className="h-5 w-px bg-white/15 mx-1" />
            <button
              onClick={() => bulkAssign("__unassigned")}
              className="h-7 px-2.5 text-xs font-medium text-amber-300 hover:bg-amber-500/15 rounded-md transition-colors"
            >
              Unassign
            </button>
            <button
              onClick={() => setSelected(new Set())}
              className="h-7 w-7 flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/10 rounded-md transition-colors"
            >
              <X size={13} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Sub-components ─────────────────────────────────────────────────────
function CapacityIndicator({ load, projectedLoad, capacity, color, isReceiving }) {
  const pct = Math.min(100, (load / capacity) * 100);
  const projectedPct = Math.min(100, (projectedLoad / capacity) * 100);
  const isOver = load > capacity;
  const isFull = load === capacity;
  return (
    <div className="flex items-center gap-1.5">
      <Users size={11} className="text-slate-400" />
      <span className={`mono text-xs ${isOver ? "text-rose-600 font-bold" : isFull ? "text-amber-700 font-semibold" : "text-slate-700 font-medium"}`}>
        {load}
        {isReceiving && projectedLoad !== load && (
          <span className="text-blue-600 font-bold"> → {projectedLoad}</span>
        )}
        <span className="text-slate-300">/</span>
        <span className="text-slate-400">{capacity}</span>
      </span>
      <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden relative">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct}%`,
            background: isOver ? "#e11d48" : isFull ? "#f59e0b" : color,
          }}
        />
        {isReceiving && projectedPct > pct && (
          <div
            className="h-full absolute top-0 transition-all"
            style={{
              left: `${pct}%`,
              width: `${projectedPct - pct}%`,
              background: "#3b82f6",
              opacity: 0.5,
            }}
          />
        )}
      </div>
    </div>
  );
}

function FilterDropdown({ label, options, selected, onToggle, onClear, count }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`h-7 px-2 text-xs font-medium rounded-md transition-all flex items-center gap-1.5 ${
          count > 0
            ? "bg-blue-50 text-blue-700 hover:bg-blue-100"
            : "text-slate-600 hover:bg-slate-100"
        }`}
      >
        <Filter size={11} className="opacity-60" />
        {label}
        {count > 0 && (
          <span className="px-1 py-0 text-[10px] font-bold rounded bg-blue-600 text-white mono leading-tight">
            {count}
          </span>
        )}
        <ChevronDown size={11} className="opacity-60" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div className="absolute top-full mt-1 left-0 min-w-[200px] max-h-72 overflow-auto bg-white border border-slate-200 rounded-lg shadow-xl py-1 z-40 fade-in scrollbar-thin">
            {count > 0 && (
              <button
                onClick={() => {
                  onClear();
                  setOpen(false);
                }}
                className="w-full px-3 py-1.5 text-xs text-left text-rose-600 hover:bg-rose-50 transition-colors flex items-center gap-2 border-b border-slate-100"
              >
                <X size={11} /> Clear filter
              </button>
            )}
            {options.map((opt) => {
              const sel = selected.has(opt.value);
              return (
                <button
                  key={opt.value}
                  onClick={() => onToggle(opt.value)}
                  className="w-full px-3 py-1.5 text-xs text-left text-slate-700 hover:bg-slate-50 transition-colors flex items-center gap-2"
                >
                  <div
                    className={`w-3.5 h-3.5 rounded-[3px] border flex items-center justify-center shrink-0 ${
                      sel ? "bg-slate-900 border-slate-900" : "border-slate-300"
                    }`}
                  >
                    {sel && <Check size={9} className="text-white" strokeWidth={3.5} />}
                  </div>
                  {opt.color && (
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: opt.color }} />
                  )}
                  <span className="flex-1 mono">{opt.label}</span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function IconButton({ children }) {
  return (
    <button
      onClick={(e) => e.stopPropagation()}
      className="w-6 h-6 flex items-center justify-center rounded hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors"
    >
      {children}
    </button>
  );
}
