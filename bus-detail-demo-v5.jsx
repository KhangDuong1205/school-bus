import React, { useState } from "react";
import {
  X,
  Clock,
  MapPin,
  Users,
  Navigation,
  Eye,
  Route as RouteIcon,
  ChevronDown,
  Phone,
  AlertCircle,
  School,
  Flag,
} from "lucide-react";

const stopsData = [
  {
    id: 1,
    time: "7:09 AM",
    address: "Luxus Hill Drive",
    area: "Luxus Hills",
    students: [
      {
        name: "Aaliyah Pangilinan",
        grade: "P4",
        parent: "Mrs. Pangilinan",
        phone: "9123 4584",
        notes: ["Allergic to peanuts", "Sit near driver"],
      },
      {
        name: "Marcus Lim",
        grade: "P4",
        parent: "Mr. Lim",
        phone: "9123 4562",
        notes: [],
      },
    ],
  },
  {
    id: 2,
    time: "7:11 AM",
    address: "Seletar Green View",
    area: "Luxus Hills",
    students: [
      {
        name: "Ezra Pueblo",
        grade: "P3",
        parent: "Mr. Pueblo",
        phone: "9123 4585",
        notes: ["Motion sickness"],
      },
    ],
  },
  {
    id: 3,
    time: "7:15 AM",
    address: "NIM Crescent",
    area: "Seletar Hills",
    students: [
      {
        name: "Zirong Wang",
        grade: "P5",
        parent: "Mrs. Wang",
        phone: "9123 4586",
        notes: [],
      },
      {
        name: "Maya Subramaniam",
        grade: "P6",
        parent: "Mr. Subramaniam",
        phone: "9123 4598",
        notes: ["Diabetic - emergency snack in bag"],
      },
      {
        name: "Theodore Ng",
        grade: "P2",
        parent: "Mrs. Ng",
        phone: "9123 4599",
        notes: ["Shy, may need help boarding"],
      },
    ],
  },
  {
    id: 4,
    time: "7:19 AM",
    address: "NIM Place",
    area: "Seletar Hills",
    students: [
      {
        name: "Sebastian Lai",
        grade: "P3",
        parent: "Mrs. Lai",
        phone: "9123 4601",
        notes: [],
      },
    ],
  },
  {
    id: 5,
    time: "7:24 AM",
    address: "Greenwich Avenue",
    area: "Seletar Hills",
    students: [
      { name: "Penelope Quek", grade: "P5", parent: "Mr. Quek", phone: "9123 4600", notes: [] },
      { name: "Violet Tham", grade: "P4", parent: "Mr. Tham", phone: "9123 4602", notes: [] },
      {
        name: "Felix Loh",
        grade: "P5",
        parent: "Mrs. Loh",
        phone: "9123 4603",
        notes: ["Wheelchair access required"],
      },
      { name: "Aurora Lim", grade: "P3", parent: "Mrs. Lim", phone: "9123 4606", notes: [] },
    ],
  },
];

const destination = {
  time: "7:35 AM",
  name: "Greenfield International School",
  address: "20 Ang Mo Kio Avenue 6",
  area: "Ang Mo Kio",
};

const gradeColors = {
  P1: "#fbbf24", P2: "#fb923c", P3: "#f87171",
  P4: "#a78bfa", P5: "#60a5fa", P6: "#34d399",
};

export default function BusDetailDemo() {
  const [open, setOpen] = useState(false);
  const [expandedStops, setExpandedStops] = useState(new Set([3]));

  const toggleStop = (id) => {
    const next = new Set(expandedStops);
    next.has(id) ? next.delete(id) : next.add(id);
    setExpandedStops(next);
  };

  return (
    <div className="min-h-screen bg-slate-100 flex items-center justify-center p-8">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
        * { font-family: 'Inter Tight', system-ui, sans-serif; }
        .mono { font-family: 'JetBrains Mono', monospace; font-feature-settings: 'tnum'; }
        .scrollbar-thin::-webkit-scrollbar { width: 8px; }
        .scrollbar-thin::-webkit-scrollbar-track { background: transparent; }
        .scrollbar-thin::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        .scrollbar-thin::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        .fade-in { animation: fadeIn 0.15s ease-out; }
        @keyframes scaleUp { from { opacity: 0; transform: scale(0.96); } to { opacity: 1; transform: scale(1); } }
        .scale-up { animation: scaleUp 0.2s cubic-bezier(0.16, 1, 0.3, 1); }
        @keyframes expandDown { from { opacity: 0; max-height: 0; } to { opacity: 1; max-height: 500px; } }
        .expand-down { animation: expandDown 0.25s ease-out; overflow: hidden; }
      `}</style>

      <div className="text-center">
        <p className="text-sm text-slate-500 mb-4">Click button bên dưới để xem modal</p>
        <button
          onClick={() => setOpen(true)}
          className="h-9 px-4 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm flex items-center gap-2 mx-auto transition-colors"
        >
          <Eye size={14} />
          View bus PB1004E details
        </button>
      </div>

      {open && (
        <>
          <div
            className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-40 fade-in"
            onClick={() => setOpen(false)}
          />

          <div className="fixed inset-0 z-50 flex items-center justify-center p-6 pointer-events-none">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-[920px] max-h-[90vh] overflow-hidden scale-up pointer-events-auto flex flex-col">
              {/* Header */}
              <div className="px-5 py-4 border-b border-slate-200 flex items-center gap-3 shrink-0">
                <div className="w-10 h-10 rounded-lg bg-blue-600 text-white flex items-center justify-center shrink-0">
                  <RouteIcon size={18} />
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-slate-900 mono">PB1004E</h2>
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">Morning route · 5 stops · Arrives 7:35 AM</p>
                </div>
                <button
                  onClick={() => setOpen(false)}
                  className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-md transition-colors"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Body */}
              <div className="flex flex-1 min-h-0">
                {/* LEFT: Stats + stops */}
                <div className="flex-1 border-r border-slate-200 flex flex-col min-w-0">
                  {/* Stats grid */}
                  <div className="grid grid-cols-4 divide-x divide-slate-200 border-b border-slate-200 shrink-0">
                    <Stat icon={Clock} label="Duration" value="20" unit="min" />
                    <Stat icon={Navigation} label="Distance" value="7.1" unit="km" />
                    <Stat icon={MapPin} label="Stops" value="5" unit="stops" />
                    <Stat icon={Users} label="Students" value="11/12" unit="pax" />
                  </div>

                  {/* Stops list */}
                  <div className="flex-1 overflow-auto scrollbar-thin">
                    <div className="px-4 pt-3 pb-2 flex items-center justify-between">
                      <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                        Route sequence · click stop to view students
                      </div>
                      <span className="text-[10px] text-slate-400">11 students total</span>
                    </div>

                    <div className="px-4 pb-4">
                      {stopsData.map((stop, idx) => {
                        const isExpanded = expandedStops.has(stop.id);
                        return (
                          <div key={stop.id} className="relative">
                            {/* Connector line - fixed height to just reach next stop */}
                            <div className="absolute left-[13px] top-9 w-0.5 bg-slate-200" style={{ height: "calc(100% - 14px)" }} />

                            <button
                              onClick={() => toggleStop(stop.id)}
                              className="relative w-full flex items-center gap-3 py-2 hover:bg-slate-50 -mx-2 px-2 rounded-md transition-colors group"
                            >
                              <div className="w-7 h-7 rounded-full ring-4 ring-white bg-blue-600 text-white text-[11px] font-bold flex items-center justify-center shrink-0 z-10">
                                {stop.id}
                              </div>
                              <div className="flex-1 min-w-0 text-left">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm font-semibold text-slate-800 truncate">
                                    {stop.address}
                                  </span>
                                  <span className="text-[11px] text-slate-400">· {stop.area}</span>
                                </div>
                                <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
                                  <span className="mono">{stop.time}</span>
                                  <span className="text-slate-300">·</span>
                                  <span className="font-semibold text-slate-700">
                                    {stop.students.length} student{stop.students.length > 1 ? "s" : ""}
                                  </span>
                                  {stop.students.some((s) => s.notes.length > 0) && (
                                    <>
                                      <span className="text-slate-300">·</span>
                                      <span className="flex items-center gap-1 text-amber-600 font-medium">
                                        <AlertCircle size={9} />
                                        Has notes
                                      </span>
                                    </>
                                  )}
                                </div>
                              </div>

                              <div className="flex -space-x-1.5">
                                {stop.students.slice(0, 3).map((s, i) => (
                                  <div
                                    key={i}
                                    className="w-6 h-6 rounded-full ring-2 ring-white flex items-center justify-center text-[9px] font-bold text-white"
                                    style={{ background: gradeColors[s.grade] }}
                                  >
                                    {s.name.split(" ").map((n) => n[0]).slice(0, 2).join("")}
                                  </div>
                                ))}
                                {stop.students.length > 3 && (
                                  <div className="w-6 h-6 rounded-full ring-2 ring-white bg-slate-200 text-slate-600 flex items-center justify-center text-[9px] font-bold">
                                    +{stop.students.length - 3}
                                  </div>
                                )}
                              </div>

                              <ChevronDown
                                size={14}
                                className={`text-slate-400 transition-transform shrink-0 ${
                                  isExpanded ? "rotate-180" : ""
                                }`}
                              />
                            </button>

                            {isExpanded && (
                              <div className="ml-9 mb-3 space-y-1.5 expand-down">
                                {stop.students.map((s, i) => (
                                  <div
                                    key={i}
                                    className="bg-white border border-slate-200 hover:border-slate-300 rounded-lg p-2.5 transition-colors group/student"
                                  >
                                    <div className="flex items-start gap-2.5">
                                      <div className="relative shrink-0">
                                        <div
                                          className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-[11px] font-bold"
                                          style={{
                                            background: `linear-gradient(135deg, ${gradeColors[s.grade]}, ${gradeColors[s.grade]}cc)`,
                                          }}
                                        >
                                          {s.name.split(" ").map((n) => n[0]).slice(0, 2).join("")}
                                        </div>
                                        <span
                                          className="absolute -bottom-1 -right-1 px-1 text-[8px] font-bold rounded mono ring-2 ring-white"
                                          style={{
                                            background: gradeColors[s.grade],
                                            color: "white",
                                          }}
                                        >
                                          {s.grade}
                                        </span>
                                      </div>

                                      <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-0.5">
                                          <span className="text-sm font-semibold text-slate-800 truncate">
                                            {s.name}
                                          </span>
                                        </div>
                                        <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mb-1.5">
                                          <span>{s.parent}</span>
                                          <span className="text-slate-300">·</span>
                                          <span className="mono">{s.phone}</span>
                                        </div>

                                        {s.notes.length > 0 && (
                                          <div className="flex flex-wrap gap-1 mt-1">
                                            {s.notes.map((note, ni) => (
                                              <span
                                                key={ni}
                                                className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-amber-50 border border-amber-200 text-amber-800 rounded text-[10px] font-medium"
                                              >
                                                <AlertCircle size={9} className="text-amber-600" />
                                                {note}
                                              </span>
                                            ))}
                                          </div>
                                        )}
                                      </div>

                                      <button
                                        className="shrink-0 h-7 px-2 text-[11px] font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-md flex items-center gap-1 transition-colors opacity-0 group-hover/student:opacity-100"
                                        title={`Call ${s.parent}`}
                                      >
                                        <Phone size={11} />
                                        Call
                                      </button>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}

                      {/* ─── Final destination ───────────────────────────── */}
                      <div className="relative mt-1">
                        <div className="relative flex items-center gap-3 py-2.5 -mx-2 px-2 bg-gradient-to-r from-emerald-50 to-transparent rounded-md">
                          {/* Destination pin - bigger, with flag icon */}
                          <div className="w-7 h-7 rounded-full ring-4 ring-white bg-emerald-600 text-white flex items-center justify-center shrink-0 z-10 shadow-sm">
                            <Flag size={12} fill="white" />
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-0.5">
                              <span className="text-[9px] font-bold text-emerald-700 uppercase tracking-wider px-1.5 py-0.5 bg-emerald-100 rounded">
                                Destination
                              </span>
                              <School size={12} className="text-emerald-600" />
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-bold text-slate-900 truncate">
                                {destination.name}
                              </span>
                            </div>
                            <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
                              <span className="mono font-semibold text-emerald-700">
                                Arrives {destination.time}
                              </span>
                              <span className="text-slate-300">·</span>
                              <span>{destination.address}, {destination.area}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* RIGHT: Map */}
                <div className="w-[280px] relative bg-slate-100 shrink-0">
                  <img
                    src="https://images.unsplash.com/photo-1524661135-423995f22d0b?w=800&q=80"
                    alt="Map view of route"
                    className="w-full h-full object-cover"
                  />
                </div>
              </div>

              {/* Footer */}
              <div className="px-5 py-3 bg-slate-50 border-t border-slate-200 flex justify-end gap-2 shrink-0">
                <button
                  onClick={() => setOpen(false)}
                  className="h-8 px-3 text-xs font-medium text-slate-600 hover:bg-slate-200 rounded-md transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Stat({ icon: Icon, label, value, unit }) {
  return (
    <div className="px-4 py-3 bg-white">
      <div className="flex items-center gap-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
        <Icon size={10} />
        {label}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-lg font-bold text-slate-900 mono">{value}</span>
        <span className="text-[10px] text-slate-400">{unit}</span>
      </div>
    </div>
  );
}
