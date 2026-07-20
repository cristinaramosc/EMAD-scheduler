import React, { useEffect, useMemo, useRef, useState } from "react";
import { DataSheetGrid, textColumn, floatColumn, keyColumn } from "react-datasheet-grid";
import "react-datasheet-grid/dist/style.css";
import "./App.css";

const API_URL = "http://127.0.0.1:8000";

const DAYS = ["Dilluns", "Dimarts", "Dimecres", "Dijous", "Divendres"];

// Fase 2 (dades acadèmiques com a taula editable): columnes per a la graella
// d'Assignatures, calcades dels camps reals que ja accepta AssignmentDTO al
// backend (POST/PATCH /academic-data/assignments). Cap canvi de model.
const ASSIGNMENT_SHEET_COLUMNS = [
  { ...keyColumn("teacher", textColumn), title: "Professor" },
  { ...keyColumn("subject", textColumn), title: "Assignatura" },
  { ...keyColumn("group", textColumn), title: "Grup" },
  { ...keyColumn("weekly_hours", floatColumn), title: "Hores setmanals" },
  { ...keyColumn("preferred_room", textColumn), title: "Aula preferida" },
  { ...keyColumn("max_session_days", textColumn), title: "Màx. dies" },
  { ...keyColumn("fixed_day", textColumn), title: "Dia fix" },
  { ...keyColumn("fixed_start", textColumn), title: "Hora fixa" },
  { ...keyColumn("consecutive_group", textColumn), title: "Consecutiva amb" },
  { ...keyColumn("notes", textColumn), title: "Notes" },
];

const HOURS = [
  "8:00",
  "8:30",
  "9:00",
  "9:30",
  "10:00",
  "10:30",
  "11:00",
  "11:30",
  "12:00",
  "12:30",
  "13:00",
  "13:30",
  "14:00",
  "14:30",
  "15:00",
  "15:30",
  "16:00",
  "16:30",
  "17:00",
  "17:30",
  "18:00",
  "18:30",
  "19:00",
  "19:30",
  "20:00",
  "20:30",
  "21:00",
];

function activityKey(activity) {
  return `${activity.day}-${activity.start}`;
}

function createTeacherRestrictionDraft(teacherName = "") {
  return {
    teacher: teacherName,
    no_gaps: false,
    max_hours_per_day: "",
    max_consecutive_hours: "",
    preferred_availability: [],
    unavailable_slots: [],
    fet_unavailable_slots: [],
  };
}

function createGroupRestrictionDraft(groupName = "") {
  return {
    group: groupName,
    no_gaps: false,
    max_hours_per_day: "",
    max_consecutive_hours: "",
    preferred_availability: [],
    unavailable_slots: [],
    fet_unavailable_slots: [],
  };
}

function parseSlotList(value) {
  return String(value || "")
    .split(/\n|,/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function formatSlotList(slots) {
  return (slots || []).join("\n");
}

function getSlotPosition(slotKey) {
  const [day, hour] = String(slotKey).split("-");
  const dayIndex = DAYS.indexOf(day);
  const hourIndex = HOURS.indexOf(hour);
  if (dayIndex < 0 || hourIndex < 0) {
    return -1;
  }
  return dayIndex * HOURS.length + hourIndex;
}

function getSlotRange(startSlot, endSlot) {
  const start = getSlotPosition(startSlot);
  const end = getSlotPosition(endSlot);
  if (start < 0 || end < 0) {
    return [];
  }

  const startIndex = Math.min(start, end);
  const endIndex = Math.max(start, end);
  const slots = [];
  for (let index = startIndex; index <= endIndex; index += 1) {
    const dayIndex = Math.floor(index / HOURS.length);
    const hourIndex = index % HOURS.length;
    if (dayIndex < DAYS.length && hourIndex < HOURS.length) {
      slots.push(`${DAYS[dayIndex]}-${HOURS[hourIndex]}`);
    }
  }
  return slots;
}

function getAvailabilitySelectionRange(startSlot, endSlot) {
  if (!startSlot || !endSlot) {
    return [];
  }

  const [startDay, startHour] = String(startSlot).split("-");
  const [endDay, endHour] = String(endSlot).split("-");
  const startDayIndex = DAYS.indexOf(startDay);
  const endDayIndex = DAYS.indexOf(endDay);
  const startHourIndex = HOURS.indexOf(startHour);
  const endHourIndex = HOURS.indexOf(endHour);

  if (startDayIndex < 0 || endDayIndex < 0 || startHourIndex < 0 || endHourIndex < 0) {
    return [];
  }

  const minDayIndex = Math.min(startDayIndex, endDayIndex);
  const maxDayIndex = Math.max(startDayIndex, endDayIndex);
  const minHourIndex = Math.min(startHourIndex, endHourIndex);
  const maxHourIndex = Math.max(startHourIndex, endHourIndex);

  const slots = [];
  for (let dayIndex = minDayIndex; dayIndex <= maxDayIndex; dayIndex += 1) {
    for (let hourIndex = minHourIndex; hourIndex <= maxHourIndex; hourIndex += 1) {
      slots.push(`${DAYS[dayIndex]}-${HOURS[hourIndex]}`);
    }
  }

  return slots;
}

function normalizeTimetableActivity(activity) {
  if (!activity) {
    return activity;
  }

  const normalized = { ...activity };
  const dayValue = String(activity.day ?? "");
  const startValue = String(activity.start ?? "");

  const dayMatch = dayValue.match(/day\s*(\d+)/i);
  if (dayMatch) {
    const dayIndex = Number(dayMatch[1]);
    normalized.day = DAYS[dayIndex] ?? dayValue;
  }

  const startMatch = startValue.match(/period\s*(\d+)/i);
  if (startMatch) {
    const startIndex = Number(startMatch[1]);
    normalized.start = HOURS[startIndex] ?? startValue;
  }

  return normalized;
}

function conflictActivityIds(conflicts) {
  return new Set(
    conflicts.flatMap((conflict) => conflict.activities || conflict.data?.activities || [])
  );
}

// Paleta de colors per identificar grups visualment al calendari (espec 01:
// "Cada grup tindrà un color principal... els colors han de servir únicament
// per identificar, no han de ser decoratius"). To muted/minimalista, no
// gradients ni ombres marcades.
const GROUP_COLOR_PALETTE = [
  { background: "#2f6f73", border: "#245b5f" }, // teal (color original, per compatibilitat visual)
  { background: "#3d5a80", border: "#2c4560" }, // blau pissarra
  { background: "#5b5f97", border: "#43466f" }, // lavanda fosc
  { background: "#6a8759", border: "#4f6642" }, // verd oliva
  { background: "#8a5a44", border: "#6b4433" }, // terracota
  { background: "#4a6670", border: "#374d55" }, // blau grisós
  { background: "#7a5c7e", border: "#5c4560" }, // malva
  { background: "#5a7d7c", border: "#436160" }, // verd maragda apagat
  { background: "#6d6875", border: "#514d58" }, // gris violaci
  { background: "#7c6a4d", border: "#5e503a" }, // marró daurat
];

function getGroupColor(groupName) {
  const key = (groupName || "").trim().toLowerCase();
  if (!key) return GROUP_COLOR_PALETTE[0];
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  }
  return GROUP_COLOR_PALETTE[hash % GROUP_COLOR_PALETTE.length];
}

function conflictMessagesByActivity(conflicts) {
  const map = new Map();
  for (const conflict of conflicts) {
    const ids = conflict.activities || conflict.data?.activities || [];
    for (const id of ids) {
      const list = map.get(id) || [];
      list.push(conflict.message || conflict.type || "Conflicte no especificat");
      map.set(id, list);
    }
  }
  return map;
}

// El backend encara no envia un camp de severitat explícit a les incidències
// (veure serialize_conflict a scheduler_use_cases.py: type, message, teacher,
// day, start, activities). Mentre no s'afegeixi, es dedueix a partir de
// `conflict.type` amb aquesta classificació. Si en algun moment el backend
// envia `conflict.severity`, es fa servir directament i es respecta.
const INCIDENT_SEVERITY_STYLES = {
  error: {
    label: "Error bloquejant",
    background: "#fdecea",
    border: "#e53935",
    text: "#b71c1c",
  },
  warning: {
    label: "Advertència",
    background: "#fff4e5",
    border: "#fb8c00",
    text: "#8a4b00",
  },
  info: {
    label: "Informació",
    background: "#e8f1fd",
    border: "#1e88e5",
    text: "#0d47a1",
  },
};

function classifyConflictSeverity(conflict) {
  if (conflict.severity && INCIDENT_SEVERITY_STYLES[conflict.severity]) {
    return conflict.severity;
  }
  const type = String(conflict.type || "").toLowerCase();
  if (/(overlap|double|solap|xoc|clash|duplicat|room_conflict|teacher_conflict|group_conflict)/.test(type)) {
    return "error";
  }
  if (/(prefer|soft|advert|warn|gap|consecutiu)/.test(type)) {
    return "warning";
  }
  return "info";
}

function resolveConflictActivities(conflict, allActivities) {
  const ids = conflict.activities || conflict.data?.activities || [];
  return ids
    .map((id) => allActivities.find((activity) => activity.id === id))
    .filter(Boolean);
}

function formatConflictField(values) {
  const unique = Array.from(new Set(values.filter(Boolean)));
  return unique.length > 0 ? unique.join(" / ") : "";
}

function getGroupParentName(groupName) {
  const trimmed = String(groupName || "").trim();
  if (!trimmed) {
    return "";
  }

  const subgroupMatch = trimmed.match(/^(.*?)(?:\s+(?:1Q|2Q))$/i);
  return subgroupMatch ? subgroupMatch[1].trim() : trimmed;
}

function isSubgroupGroupName(groupName) {
  return /(?:^|\s)(?:1Q|2Q)$/i.test(String(groupName || "").trim());
}

function getVisibleActivitiesForSlot(slotActivities, selectedGroup) {
  if (!selectedGroup) {
    return [];
  }

  const matchingActivities = (slotActivities || []).filter((activity) => {
    return getGroupParentName(activity?.group) === selectedGroup;
  });

  if (!matchingActivities.length) {
    return [];
  }

  const hasFullParentActivity = matchingActivities.some((activity) => activity?.group === selectedGroup);
  if (hasFullParentActivity) {
    return matchingActivities.filter((activity) => activity?.group === selectedGroup);
  }

  const visibleActivities = [];
  const seenSubgroups = new Set();

  matchingActivities.forEach((activity) => {
    const subgroupKey = isSubgroupGroupName(activity?.group) ? activity.group : null;
    if (!subgroupKey) {
      return;
    }

    if (seenSubgroups.has(subgroupKey)) {
      return;
    }

    seenSubgroups.add(subgroupKey);
    visibleActivities.push(activity);
  });

  return visibleActivities.filter((activity) => isSubgroupGroupName(activity?.group));
}

function getQuarterSuffix(value) {
  const text = String(value || "").trim();
  const match = text.match(/(?:\s|^)(1Q|2Q)$/i);
  return match ? match[1].toUpperCase() : null;
}

function canShareSlotWithQuarter(existingActivity, candidateActivity) {
  if (!existingActivity || !candidateActivity) {
    return false;
  }

  if (getGroupParentName(existingActivity.group) !== getGroupParentName(candidateActivity.group)) {
    return false;
  }

  const existingSuffix = getQuarterSuffix(existingActivity.subject) || getQuarterSuffix(existingActivity.group);
  const candidateSuffix = getQuarterSuffix(candidateActivity.subject) || getQuarterSuffix(candidateActivity.group);

  return existingSuffix && candidateSuffix && existingSuffix !== candidateSuffix;
}

export default function App() {
  const workbookInputRef = useRef(null);
  const fetInputRef = useRef(null);
  const academicSpreadsheetInputRef = useRef(null);
  const [isImportingSpreadsheet, setIsImportingSpreadsheet] = useState(false);
  const [activities, setActivities] = useState([]);
  const [conflicts, setConflicts] = useState([]);
  const [academicSummary, setAcademicSummary] = useState(null);
  const [academicSubjects, setAcademicSubjects] = useState([]);
  const [generationStats, setGenerationStats] = useState(null);
  const [generatedUnscheduledActivities, setGeneratedUnscheduledActivities] = useState([]);
  const [draggedActivityId, setDraggedActivityId] = useState(null);
  const [dropTarget, setDropTarget] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isFetchingEntities, setIsFetchingEntities] = useState(false);
  const [teachers, setTeachers] = useState([]);
  const [groups, setGroups] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [teachingAssignments, setTeachingAssignments] = useState([]);
  const [useSpreadsheetView, setUseSpreadsheetView] = useState(false);
  const [spreadsheetRows, setSpreadsheetRows] = useState([]);
  const [spreadsheetOriginalRows, setSpreadsheetOriginalRows] = useState([]);
  const [isSavingSpreadsheet, setIsSavingSpreadsheet] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isExportingTemplates, setIsExportingTemplates] = useState(false);
  const [isImportingWorkbook, setIsImportingWorkbook] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [suggestionsByActivity, setSuggestionsByActivity] = useState({});
  const [isTogglingBreak, setIsTogglingBreak] = useState(false);
  const [isAccepting, setIsAccepting] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [proposal, setProposal] = useState(null);
  const [proposals, setProposals] = useState([]);
  const [selectedProposalId, setSelectedProposalId] = useState(null);
  const [selectedActivityId, setSelectedActivityId] = useState(null);
  const [selectedExplanation, setSelectedExplanation] = useState(null);
  const [isLoadingExplanation, setIsLoadingExplanation] = useState(false);
  const [explanationError, setExplanationError] = useState("");
  const [timetableView, setTimetableView] = useState("group");
  const [timetableEntity, setTimetableEntity] = useState("");
  const [selectedGroup, setSelectedGroup] = useState("");
  const [teacherFilter, setTeacherFilter] = useState("");
  const [currentScreen, setCurrentScreen] = useState("timetable");
  const [academicTab, setAcademicTab] = useState("teachers");

  const [teacherDraft, setTeacherDraft] = useState({ name: "", short_name: "", active: true });
  const [teacherEdit, setTeacherEdit] = useState(null);
  const [teacherEditValues, setTeacherEditValues] = useState({ name: "", short_name: "", active: true });
  const [teacherRestrictions, setTeacherRestrictions] = useState([]);
  const [teacherRestrictionEditor, setTeacherRestrictionEditor] = useState("");
  const [teacherRestrictionDraft, setTeacherRestrictionDraft] = useState(createTeacherRestrictionDraft(""));
  const [isSavingTeacherRestrictions, setIsSavingTeacherRestrictions] = useState(false);
  const [groupRestrictions, setGroupRestrictions] = useState([]);
  const [groupRestrictionDraft, setGroupRestrictionDraft] = useState(createGroupRestrictionDraft(""));
  const [isSavingGroupRestrictions, setIsSavingGroupRestrictions] = useState(false);
  const [availabilitySelectionAnchor, setAvailabilitySelectionAnchor] = useState(null);
  const [unavailableSelectionAnchor, setUnavailableSelectionAnchor] = useState(null);

  const [groupDraft, setGroupDraft] = useState({ name: "", course: "", active: true });
  const [groupEdit, setGroupEdit] = useState(null);
  const [groupEditValues, setGroupEditValues] = useState({ name: "", course: "", active: true });

  const [subjectDraft, setSubjectDraft] = useState({ name: "", weekly_hours: "", allowed_session_lengths: "" });
  const [subjectEdit, setSubjectEdit] = useState(null);
  const [subjectEditValues, setSubjectEditValues] = useState({ name: "", weekly_hours: "", allowed_session_lengths: "" });

  const [roomDraft, setRoomDraft] = useState({ name: "", capacity: "" });
  const [roomEdit, setRoomEdit] = useState(null);
  const [roomEditValues, setRoomEditValues] = useState({ name: "", capacity: "" });

  const [assignmentDraft, setAssignmentDraft] = useState({ teacher: "", subject: "", group: "", weekly_hours: "", fixed_day: "", fixed_start: "", max_session_days: "", consecutive_group: "" });
  const [selectedAssignmentIds, setSelectedAssignmentIds] = useState([]);
  const [assignmentEdit, setAssignmentEdit] = useState(null);
  const [assignmentEditValues, setAssignmentEditValues] = useState({ teacher: "", subject: "", group: "", weekly_hours: "", allowed_session_lengths: "", fixed_day: "", fixed_start: "", max_session_days: "", consecutive_group: "" });

  function parseSessionLengths(value) {
    return value
      .split("+")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => parseFloat(part))
      .filter((value) => !Number.isNaN(value));
  }

  function formatSessionLengths(lengths) {
    if (!Array.isArray(lengths)) {
      return "";
    }
    return lengths.map((value) => String(value)).join("+");
  }

  function normalizeTeachingAssignment(assignment, index = 0) {
    const source = assignment?.record || assignment || {};
    const teacher = source.teacher ?? source.teacher_name ?? source.teacherName ?? source.professor ?? "";
    const subject = source.subject ?? source.subject_name ?? source.subjectName ?? "";
    const group = source.group ?? source.group_name ?? source.groupName ?? "";
    const weeklyHours = source.weekly_hours ?? source.weeklyHours ?? source.hours ?? source.weekly_hours ?? 0;
    const allowedSessionLengths = source.allowed_session_lengths ?? source.allowedSessionLengths ?? [];

    return {
      ...source,
      id: source.id ?? source.assignment_id ?? source.assignmentId ?? source.uuid ?? `${teacher}-${group}-${subject}-${index}`,
      teacher,
      subject,
      group,
      weekly_hours: weeklyHours,
      allowed_session_lengths: Array.isArray(allowedSessionLengths)
        ? allowedSessionLengths
        : parseSessionLengths(String(allowedSessionLengths || "")),
    };
  }

  async function loadData() {
    setIsLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_URL}/scheduler/state`);
      const data = await response.json();

      setActivities((data.activities || []).map(normalizeTimetableActivity));
      setConflicts(data.conflicts || []);
      setProposal(data.proposal || null);
      setGenerationStats(data.generation_stats || null);
      setGeneratedUnscheduledActivities(data.unscheduled_activities || []);
    } catch {
      setError("No s'ha pogut carregar l'horari.");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadAcademicSummary() {
    try {
      const response = await fetch(`${API_URL}/academic-data/summary`);
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      setAcademicSummary(data);
      // fetch subjects with allowed session lengths
      try {
        const subjResp = await fetch(`${API_URL}/academic-data/subjects`);
        if (subjResp.ok) {
          const subjData = await subjResp.json();
          setAcademicSubjects(subjData || []);
        }
      } catch {
        // ignore
      }
    } catch {
      // ignore summary refresh errors to avoid blocking scheduler UI
    }
  }

  async function loadTimetableEntities() {
    setIsFetchingEntities(true);

    try {
      const [teachersResp, groupsResp, roomsResp] = await Promise.all([
        fetch(`${API_URL}/academic-data/teachers`),
        fetch(`${API_URL}/academic-data/groups`),
        fetch(`${API_URL}/academic-data/rooms`),
      ]);

      if (teachersResp.ok) {
        setTeachers(await teachersResp.json());
      }
      if (groupsResp.ok) {
        setGroups(await groupsResp.json());
      }
      if (roomsResp.ok) {
        setRooms(await roomsResp.json());
      }
      // fetch subjects and assignments too
      try {
        const [subjectsResp, assignmentsResp] = await Promise.all([
          fetch(`${API_URL}/academic-data/subjects`),
          fetch(`${API_URL}/academic-data/assignments`),
        ]);

        if (subjectsResp.ok) {
          const subj = await subjectsResp.json();
          setAcademicSubjects(subj || []);
        }
        if (assignmentsResp.ok) {
          const ass = await assignmentsResp.json();
          const assignmentsPayload = Array.isArray(ass)
            ? ass
            : Array.isArray(ass?.assignments)
              ? ass.assignments
              : [];
          setTeachingAssignments(assignmentsPayload.map((assignment, index) => normalizeTeachingAssignment(assignment, index)));
        }
      } catch {
        // ignore
      }
    } catch {
      // ignore entity load failures; timetable still works
    } finally {
      setIsFetchingEntities(false);
    }
  }

  async function loadTeacherRestrictions() {
    if (!teachers.length) {
      setTeacherRestrictions([]);
      return;
    }

    try {
      const results = await Promise.all(
        teachers.map(async (teacher) => {
          const response = await fetch(`${API_URL}/academic-data/teachers/${encodeURIComponent(teacher.name)}/restrictions`);
          if (!response.ok) {
            return createTeacherRestrictionDraft(teacher.name);
          }

          const data = await response.json();
          return {
            ...createTeacherRestrictionDraft(teacher.name),
            ...data,
            teacher: data.teacher || teacher.name,
            no_gaps: Boolean(data.no_gaps),
            max_hours_per_day: data.max_hours_per_day ?? "",
            max_consecutive_hours: data.max_consecutive_hours ?? "",
            preferred_availability: Array.isArray(data.preferred_availability) ? data.preferred_availability : [],
            unavailable_slots: Array.isArray(data.unavailable_slots) ? data.unavailable_slots : [],
          };
        })
      );

      setTeacherRestrictions(results);
    } catch {
      // ignore restriction loading failures
    }
  }

  async function openTeacherRestrictionEditor(teacherName) {
    if (!teacherName) {
      setTeacherRestrictionEditor("");
      setTeacherRestrictionDraft(createTeacherRestrictionDraft(""));
      return;
    }

    const existing = teacherRestrictions.find((item) => item.teacher === teacherName);
    if (existing) {
      setTeacherRestrictionEditor(teacherName);
      setTeacherRestrictionDraft({
        ...createTeacherRestrictionDraft(teacherName),
        ...existing,
        teacher: teacherName,
        preferred_availability: Array.isArray(existing.preferred_availability) ? existing.preferred_availability : [],
        unavailable_slots: Array.isArray(existing.unavailable_slots) ? existing.unavailable_slots : [],
      });
      return;
    }

    try {
      const response = await fetch(`${API_URL}/academic-data/teachers/${encodeURIComponent(teacherName)}/restrictions`);
      if (!response.ok) {
        setTeacherRestrictionEditor(teacherName);
        setTeacherRestrictionDraft(createTeacherRestrictionDraft(teacherName));
        return;
      }

      const data = await response.json();
      setTeacherRestrictionEditor(teacherName);
      setTeacherRestrictionDraft({
        ...createTeacherRestrictionDraft(teacherName),
        ...data,
        teacher: teacherName,
        no_gaps: Boolean(data.no_gaps),
        max_hours_per_day: data.max_hours_per_day ?? "",
        max_consecutive_hours: data.max_consecutive_hours ?? "",
        preferred_availability: Array.isArray(data.preferred_availability) ? data.preferred_availability : [],
        unavailable_slots: Array.isArray(data.unavailable_slots) ? data.unavailable_slots : [],
      });
    } catch {
      setTeacherRestrictionEditor(teacherName);
      setTeacherRestrictionDraft(createTeacherRestrictionDraft(teacherName));
    }
  }

  async function saveTeacherRestrictions() {
    if (!teacherRestrictionDraft.teacher) {
      return;
    }

    setIsSavingTeacherRestrictions(true);
    setError("");
    setSuccessMessage("");

    try {
      const payload = {
        teacher: teacherRestrictionDraft.teacher,
        no_gaps: Boolean(teacherRestrictionDraft.no_gaps),
        max_hours_per_day: teacherRestrictionDraft.max_hours_per_day === "" ? null : Number(teacherRestrictionDraft.max_hours_per_day),
        max_consecutive_hours: teacherRestrictionDraft.max_consecutive_hours === "" ? null : Number(teacherRestrictionDraft.max_consecutive_hours),
        preferred_availability: teacherRestrictionDraft.preferred_availability || [],
        unavailable_slots: teacherRestrictionDraft.unavailable_slots || [],
      };

      const response = await fetch(`${API_URL}/academic-data/teachers/${encodeURIComponent(teacherRestrictionDraft.teacher)}/restrictions`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.detail || "No s'ha pogut desar les restriccions del professor.");
      }

      await loadTeacherRestrictions();
      setSuccessMessage(`Restriccions desades per ${teacherRestrictionDraft.teacher}.`);
    } catch (err) {
      setError(err.message || "No s'ha pogut desar les restriccions del professor.");
    } finally {
      setIsSavingTeacherRestrictions(false);
    }
  }

  function renderTeacherRestrictionEditor() {
    if (!teacherRestrictionEditor) {
      return (
        <p className="muted">Seleccioneu un professor de la llista per editar-ne les hores disponibles i les restriccions.</p>
      );
    }

    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>{teacherRestrictionEditor}</h3>
          <button type="button" onClick={() => openTeacherRestrictionEditor("")}>Tanca</button>
        </div>

        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              checked={Boolean(teacherRestrictionDraft.no_gaps)}
              onChange={(event) => setTeacherRestrictionDraft({ ...teacherRestrictionDraft, no_gaps: event.target.checked })}
            />
            Sense buits
          </label>
          <label>
            Màx. hores per dia
            <input
              type="number"
              min="0"
              value={teacherRestrictionDraft.max_hours_per_day}
              onChange={(event) => setTeacherRestrictionDraft({ ...teacherRestrictionDraft, max_hours_per_day: event.target.value })}
              style={{ marginLeft: 8, width: 64 }}
            />
          </label>
          <label>
            Màx. hores consecutives
            <input
              type="number"
              min="0"
              value={teacherRestrictionDraft.max_consecutive_hours}
              onChange={(event) => setTeacherRestrictionDraft({ ...teacherRestrictionDraft, max_consecutive_hours: event.target.value })}
              style={{ marginLeft: 8, width: 64 }}
            />
          </label>
        </div>

        <div style={{ marginBottom: 16 }}>
          <h4 style={{ marginBottom: 6 }}>Disponibilitat preferida</h4>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            <button type="button" onClick={() => applyAvailabilityPreset("matí", teacherRestrictionDraft, setTeacherRestrictionDraft)}>Matí</button>
            <button type="button" onClick={() => applyAvailabilityPreset("tarda", teacherRestrictionDraft, setTeacherRestrictionDraft)}>Tarda</button>
            <button type="button" onClick={() => applyAvailabilityPreset("dia-complet", teacherRestrictionDraft, setTeacherRestrictionDraft)}>Dia complet</button>
            <button type="button" onClick={() => clearAvailabilitySelection(teacherRestrictionDraft, setTeacherRestrictionDraft)}>Neteja selecció</button>
          </div>
          <div className="muted">Clic simple per activar o desactivar una franja. Maj + clic per seleccionar un rang.</div>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Dia</th>
                  {HOURS.map((hour) => (
                    <th key={hour} style={{ minWidth: 42 }}>{hour}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {DAYS.map((day) => (
                  <tr key={day}>
                    <td>{day}</td>
                    {HOURS.map((hour) => {
                      const slotKey = `${day}-${hour}`;
                      const isPreferred = teacherRestrictionDraft.preferred_availability.includes(slotKey);
                      return (
                        <td key={slotKey}>
                          <button
                            type="button"
                            onMouseDown={(event) => { event.preventDefault(); if (!event.shiftKey) setAvailabilitySelectionAnchor(slotKey); }}
                            onClick={(event) => updateAvailabilitySelection(slotKey, event, teacherRestrictionDraft, setTeacherRestrictionDraft)}
                            style={{
                              width: 16,
                              height: 16,
                              padding: 0,
                              border: `1px solid ${isPreferred ? "#4f46e5" : "#cbd5e1"}`,
                              background: isPreferred ? "#c7d2fe" : "#fff",
                            }}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <h4 style={{ marginBottom: 6 }}>Franges no disponibles</h4>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            <button type="button" onClick={() => applyUnavailablePreset("no-abans-10", teacherRestrictionDraft, setTeacherRestrictionDraft)}>No abans de les 10:00</button>
            <button type="button" onClick={() => applyUnavailablePreset("no-abans-15", teacherRestrictionDraft, setTeacherRestrictionDraft)}>No abans de les 15:00</button>
            <button type="button" onClick={() => applyUnavailablePreset("no-despres-17", teacherRestrictionDraft, setTeacherRestrictionDraft)}>No després de les 17:00</button>
            <button type="button" onClick={() => applyUnavailablePreset("entre-10-14", teacherRestrictionDraft, setTeacherRestrictionDraft)}>Entre les 10:00 i les 14:00</button>
            <button type="button" onClick={() => applyUnavailablePreset("nomes-matins", teacherRestrictionDraft, setTeacherRestrictionDraft)}>Només matins</button>
            <button type="button" onClick={() => applyUnavailablePreset("nomes-tardes", teacherRestrictionDraft, setTeacherRestrictionDraft)}>Només tardes</button>
            <button type="button" onClick={() => clearAvailabilitySelection(teacherRestrictionDraft, setTeacherRestrictionDraft, "unavailable_slots", setUnavailableSelectionAnchor)}>Neteja selecció</button>
          </div>
          <div className="muted">Clic simple per marcar/desmarcar una franja no disponible manualment (vermell). Maj + clic per seleccionar un rang. Les caselles taronges venen del fitxer FET i no s'editen aquí.</div>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Dia</th>
                  {HOURS.map((hour) => (
                    <th key={hour} style={{ minWidth: 42 }}>{hour}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {DAYS.map((day) => (
                  <tr key={day}>
                    <td>{day}</td>
                    {HOURS.map((hour) => {
                      const slotKey = `${day}-${hour}`;
                      const isUnavailable = teacherRestrictionDraft.unavailable_slots.includes(slotKey);
                      const isFromFet = (teacherRestrictionDraft.fet_unavailable_slots || []).includes(`${day} ${hour}`);
                      return (
                        <td key={slotKey}>
                          <button
                            type="button"
                            title={isFromFet ? "No disponible segons el fitxer FET" : undefined}
                            onMouseDown={(event) => { event.preventDefault(); if (!event.shiftKey) setUnavailableSelectionAnchor(slotKey); }}
                            onClick={(event) => updateAvailabilitySelection(slotKey, event, teacherRestrictionDraft, setTeacherRestrictionDraft, "unavailable_slots", unavailableSelectionAnchor, setUnavailableSelectionAnchor)}
                            style={{
                              width: 16,
                              height: 16,
                              padding: 0,
                              border: `1px solid ${isUnavailable ? "#b91c1c" : isFromFet ? "#c2680d" : "#cbd5e1"}`,
                              background: isUnavailable ? "#fecaca" : isFromFet ? "#fed7aa" : "#fff",
                            }}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <button type="button" onClick={saveTeacherRestrictions} disabled={isSavingTeacherRestrictions}>
          {isSavingTeacherRestrictions ? "S'està desant..." : "Desa restriccions"}
        </button>
      </div>
    );
  }

  async function loadGroupRestrictions(groupName) {
    if (!groupName) {
      setGroupRestrictionDraft(createGroupRestrictionDraft(""));
      setGroupRestrictions([]);
      return;
    }

    try {
      const response = await fetch(`${API_URL}/academic-data/groups/${encodeURIComponent(groupName)}/restrictions`);
      if (!response.ok) {
        setGroupRestrictionDraft(createGroupRestrictionDraft(groupName));
        return;
      }

      const data = await response.json();
      const nextDraft = {
        ...createGroupRestrictionDraft(groupName),
        ...data,
        group: data.group || groupName,
        no_gaps: Boolean(data.no_gaps),
        max_hours_per_day: data.max_hours_per_day ?? "",
        max_consecutive_hours: data.max_consecutive_hours ?? "",
        preferred_availability: Array.isArray(data.preferred_availability) ? data.preferred_availability : [],
        unavailable_slots: Array.isArray(data.unavailable_slots) ? data.unavailable_slots : [],
      };
      setGroupRestrictionDraft(nextDraft);
      setGroupRestrictions((current) => {
        const others = current.filter((item) => item.group !== groupName);
        return [...others, { ...nextDraft, group: groupName }];
      });
    } catch {
      setGroupRestrictionDraft(createGroupRestrictionDraft(groupName));
    }
  }

  async function saveGroupRestrictions(updatedDraft = groupRestrictionDraft) {
    if (!updatedDraft.group) {
      return;
    }

    setIsSavingGroupRestrictions(true);
    setError("");
    setSuccessMessage("");

    try {
      const payload = {
        group: updatedDraft.group,
        no_gaps: Boolean(updatedDraft.no_gaps),
        max_hours_per_day: updatedDraft.max_hours_per_day === "" ? null : Number(updatedDraft.max_hours_per_day),
        max_consecutive_hours: updatedDraft.max_consecutive_hours === "" ? null : Number(updatedDraft.max_consecutive_hours),
        preferred_availability: updatedDraft.preferred_availability || [],
        unavailable_slots: updatedDraft.unavailable_slots || [],
      };

      const response = await fetch(`${API_URL}/academic-data/groups/${encodeURIComponent(updatedDraft.group)}/restrictions`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.detail || "No s'ha pogut desar les restriccions del grup.");
      }

      await loadGroupRestrictions(updatedDraft.group);
      await loadTimetableEntities();
      setSuccessMessage(`Restriccions desades per ${updatedDraft.group}.`);
    } catch (err) {
      setError(err.message || "No s'ha pogut desar les restriccions del grup.");
    } finally {
      setIsSavingGroupRestrictions(false);
    }
  }

  async function toggleSelectedGroupNoGaps() {
    if (!selectedGroup) {
      return;
    }

    const nextDraft = {
      ...createGroupRestrictionDraft(selectedGroup),
      ...groupRestrictionDraft,
      group: selectedGroup,
      no_gaps: !Boolean(groupRestrictionDraft.no_gaps),
    };

    setGroupRestrictionDraft(nextDraft);
    await saveGroupRestrictions(nextDraft);
  }

  async function loadFetData(file) {
    setIsLoading(true);
    setError("");

    try {
      const requestOptions = {
        method: "POST",
      };

      if (file) {
        const formData = new FormData();
        formData.append("file", file);

         console.log(file);
  console.log(file?.name);
  console.log(file?.size);
        requestOptions.body = formData;
      }

      const response = await fetch(`${API_URL}/scheduler/load-fet`, requestOptions);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "No s'ha pogut carregar el fitxer FET.");
      }

      setActivities((data.activities || []).map(normalizeTimetableActivity));
      setConflicts(data.conflicts || []);
      setProposal(null);
      setGenerationStats(null);
      setGeneratedUnscheduledActivities([]);
      // refresh academic lists produced by FET import
      await loadAcademicSummary();
      await loadTimetableEntities();
    } catch {
      setError("No s'ha pogut carregar el fitxer FET.");
    } finally {
      setIsLoading(false);
    }
  }

  function openFetSelector() {
    fetInputRef.current?.click();
  }

  async function downloadSpreadsheet(url, fallbackName) {
    setError("");
    setSuccessMessage("");
    try {
      const response = await fetch(url);
      if (!response.ok) {
        setError("No s'ha pogut descarregar el full de càlcul.");
        return;
      }
      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      const disposition = response.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename=([^;]+)/);
      link.download = match ? match[1].trim() : fallbackName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch {
      setError("No s'ha pogut descarregar el full de càlcul.");
    }
  }

  function downloadBlankSpreadsheet() {
    return downloadSpreadsheet(`${API_URL}/academic-data/spreadsheet/blank`, "EMAD-model-buit.xlsx");
  }

  function downloadCurrentSpreadsheet() {
    return downloadSpreadsheet(`${API_URL}/academic-data/spreadsheet/current`, "EMAD-dades-actuals.xlsx");
  }

  async function onAcademicSpreadsheetSelected(event) {
    const file = event.target?.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (!window.confirm("Això substituirà tots els professors, grups, assignatures i aules actuals pel contingut d'aquest full de càlcul. Vols continuar?")) {
      return;
    }

    setIsImportingSpreadsheet(true);
    setError("");
    setSuccessMessage("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_URL}/academic-data/spreadsheet/import`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.detail || "No s'ha pogut importar el full de càlcul.");
        return;
      }
      setSuccessMessage(
        `Importat: ${data.teachers} professors, ${data.groups} grups, ${data.assignments} assignacions, ${data.rooms} aules.`
      );
      await refreshAcademicLists();
      await loadTeacherRestrictions();
    } catch {
      setError("No s'ha pogut importar el full de càlcul.");
    } finally {
      setIsImportingSpreadsheet(false);
    }
  }

  async function onFetFileSelected(event) {
    const file = event.target?.files?.[0];
    if (!file) {
      return;
    }

    await loadFetData(file);
    event.target.value = "";
  }

  async function generateProposal() {
    setIsGenerating(true);
    setError("");
    setSuccessMessage("");

    try {
      const response = await fetch(`${API_URL}/scheduler/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          requirement_ids: [],
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "No s'ha pogut generar la proposta.");
      }

      setProposal(data.best_proposal || null);
      setProposals(data.proposals || []);
      setSelectedProposalId(data.best_proposal?.id || (data.proposals?.[0]?.id || null));
      setGenerationStats(data.statistics || null);
      setGeneratedUnscheduledActivities(data.unscheduled_activities || []);
      const activeProposal = data.proposals?.find((p) => p.id === (data.best_proposal?.id || (data.proposals?.[0]?.id || null))) || data.best_proposal;
      setActivities(((activeProposal?.activities || data.best_proposal?.activities) || []).map((activity) => ({
        ...normalizeTimetableActivity(activity),
        id: activity.id,
        subject: activity.subject,
        teacher: activity.teacher,
        group: activity.group,
        room: activity.room,
        day: normalizeTimetableActivity(activity).day,
        start: normalizeTimetableActivity(activity).start,
      })));
      setConflicts(data.best_proposal?.conflicts || []);
      await refreshAcademicLists();
    } catch (err) {
      setProposal(null);
      setGenerationStats(null);
      setGeneratedUnscheduledActivities([]);
      setError(err.message || "No s'ha pogut generar la proposta.");
    } finally {
      setIsGenerating(false);
    }
  }

  async function generateExcelTemplates() {
    setIsExportingTemplates(true);
    setError("");
    setSuccessMessage("");

    try {
      const response = await fetch(`${API_URL}/exports/excel/templates/generate`, {
        method: "POST",
      });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        throw new Error(data.detail || "No s'han pogut generar les plantilles Excel.");
      }

      setSuccessMessage(
        `Plantilles Excel generades (${data.files?.length || 0} fitxers) a: ${data.output_folder}`
      );
    } catch (err) {
      setError(err.message || "No s'han pogut generar les plantilles Excel.");
    } finally {
      setIsExportingTemplates(false);
    }
  }

  function openWorkbookSelector() {
    workbookInputRef.current?.click();
  }

  async function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        const parts = result.split(",");
        resolve(parts.length > 1 ? parts[1] : "");
      };
      reader.onerror = () => reject(new Error("No s'ha pogut llegir el fitxer"));
      reader.readAsDataURL(file);
    });
  }

  async function importAcademicWorkbook(event) {
    const selected = Array.from(event.target.files || []);
    if (selected.length === 0) {
      return;
    }

    setIsImportingWorkbook(true);
    setError("");
    setSuccessMessage("");

    try {
      const files = await Promise.all(
        selected.map(async (file) => ({
          name: file.name,
          workbook_base64: await readFileAsBase64(file),
        }))
      );

      const response = await fetch(`${API_URL}/imports/excel/academic-workbook/import`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ files }),
      });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        const issues = data?.detail?.issues || [];
        if (issues.length > 0) {
          const formatted = issues
            .slice(0, 4)
            .map((issue) => `${issue.worksheet} R${issue.row}${issue.column}: ${issue.message}`)
            .join(" | ");
          throw new Error(`Errors de validació: ${formatted}`);
        }
        throw new Error(data?.detail || "No s'ha pogut importar el workbook acadèmic.");
      }

      setSuccessMessage(
        `Teachers imported: ${data.summary?.teachers_imported || 0} · Groups imported: ${data.summary?.groups_imported || 0} · Subjects imported: ${data.summary?.subjects_imported || 0} · Teaching assignments: ${data.summary?.teaching_assignments || 0} · Warnings: ${data.summary?.warnings || 0}`
      );

      await loadAcademicSummary();
      await loadTimetableEntities();
      await loadData();
    } catch (err) {
      setError(err.message || "No s'ha pogut importar el workbook acadèmic.");
    } finally {
      setIsImportingWorkbook(false);
      event.target.value = "";
    }
  }

  async function acceptProposal() {
    if (!proposal?.id) {
      return;
    }

    setIsAccepting(true);
    setError("");
    setSuccessMessage("");

    try {
      const response = await fetch(`${API_URL}/scheduler/proposal/${proposal.id}/accept`, {
        method: "POST",
      });
      const data = await response.json();

      if (!response.ok || !data.ok) {
        if (data.error === "unscheduled_activities_pending") {
          throw new Error("Encara hi ha activitats sense franja. Cal ubicar-les abans d'acceptar la proposta.");
        }
        throw new Error(data.detail || "No s'ha pogut acceptar la proposta.");
      }

      setProposal(null);
      setGenerationStats(null);
      setGeneratedUnscheduledActivities([]);
      setSuccessMessage("La proposta s'ha acceptat i ara és l'horari actiu.");
      await loadData();
    } catch (err) {
      setError(err.message || "No s'ha pogut acceptar la proposta.");
    } finally {
      setIsAccepting(false);
    }
  }

  useEffect(() => {
    loadData();
    loadAcademicSummary();
    loadTimetableEntities();
  }, []);

  useEffect(() => {
    if (!selectedProposalId || !proposals.length) return;
    const selected = proposals.find((p) => p.id === selectedProposalId) || null;
    if (!selected) return;
    setProposal(selected);
    setActivities((selected.activities || []).map((activity) => ({
      ...normalizeTimetableActivity(activity),
      id: activity.id,
      subject: activity.subject,
      teacher: activity.teacher,
      group: activity.group,
      room: activity.room,
      day: normalizeTimetableActivity(activity).day,
      start: normalizeTimetableActivity(activity).start,
    })));
    setConflicts(selected.conflicts || []);
  }, [selectedProposalId]);

  useEffect(() => {
    if (currentScreen === "academic" && (academicTab === "teachers" || academicTab === "teacher-restrictions")) {
      loadTeacherRestrictions();
    }
  }, [currentScreen, academicTab, teachers.length]);

  const timetableGroupOptions = useMemo(() => {
    const parentGroups = [];
    const seenGroups = new Set();

    groups.forEach((group) => {
      const parentName = getGroupParentName(group?.name);
      if (!parentName || seenGroups.has(parentName)) {
        return;
      }

      seenGroups.add(parentName);
      parentGroups.push({ name: parentName });
    });

    return parentGroups;
  }, [groups]);

  useEffect(() => {
    if (!timetableGroupOptions.length) {
      setSelectedGroup("");
      return;
    }

    setSelectedGroup((current) => {
      if (current && timetableGroupOptions.some((group) => group.name === current)) {
        return current;
      }
      return timetableGroupOptions[0]?.name || "";
    });
  }, [timetableGroupOptions]);

  useEffect(() => {
    if (selectedGroup) {
      loadGroupRestrictions(selectedGroup);
    }
  }, [selectedGroup]);

  const filteredActivities = useMemo(() => {
    let nextActivities = activities;

    if (selectedGroup) {
      nextActivities = nextActivities.filter((activity) => getGroupParentName(activity?.group) === selectedGroup);
    }

    if (teacherFilter) {
      nextActivities = nextActivities.filter((activity) => activity.teacher === teacherFilter);
    }

    return nextActivities;
  }, [activities, selectedGroup, teacherFilter]);

  const groupBreakDays = useMemo(() => {
    if (!selectedGroup) return new Set();
    return new Set(
      activities
        .filter(
          (activity) =>
            activity.group === selectedGroup &&
            (activity.subject || "").trim().toLowerCase() === "descans"
        )
        .map((activity) => activity.day)
    );
  }, [activities, selectedGroup]);

  const activitiesBySlot = useMemo(() => {
    return filteredActivities.reduce((slots, activity) => {
      const key = activityKey(activity);

      if (!slots[key]) {
        slots[key] = [];
      }

      slots[key].push(activity);

      return slots;
    }, {});
  }, [filteredActivities]);

  const visibleActivitiesBySlot = useMemo(() => {
    return Object.entries(activitiesBySlot).reduce((slots, [slotKey, slotActivities]) => {
      slots[slotKey] = getVisibleActivitiesForSlot(slotActivities, selectedGroup);
      return slots;
    }, {});
  }, [activitiesBySlot, selectedGroup]);

  const conflictIds = useMemo(() => conflictActivityIds(conflicts), [conflicts]);
  const conflictMessages = useMemo(() => conflictMessagesByActivity(conflicts), [conflicts]);

  const unscheduledActivities = useMemo(() => {
    return activities.filter(
      (activity) => !DAYS.includes(activity.day) || !HOURS.includes(activity.start)
    );
  }, [activities]);

  const displayedUnscheduledActivities = proposal
    ? generatedUnscheduledActivities
    : unscheduledActivities;

  async function addManualActivity(payload) {
    setError("");
    setSuccessMessage("");
    try {
      const response = await fetch(`${API_URL}/scheduler/activities`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!data.ok) {
        setError(
          data.error === "validation_failed"
            ? "No es pot afegir aquí: xoca amb una altra activitat."
            : "No s'ha pogut afegir l'activitat."
        );
        return false;
      }
      setActivities((data.activities || []).map(normalizeTimetableActivity));
      setConflicts(data.conflicts || []);
      setSuccessMessage("Activitat afegida correctament.");
      return true;
    } catch {
      setError("No s'ha pogut afegir l'activitat.");
      return false;
    }
  }

  async function deleteActivity(activityId) {
    setError("");
    setSuccessMessage("");
    try {
      const response = await fetch(`${API_URL}/scheduler/activities/${activityId}`, { method: "DELETE" });
      const data = await response.json();
      if (!data.ok) {
        setError("No s'ha pogut eliminar l'activitat.");
        return;
      }
      setActivities((data.activities || []).map(normalizeTimetableActivity));
      setConflicts(data.conflicts || []);
      setSuccessMessage("Activitat eliminada.");
    } catch {
      setError("No s'ha pogut eliminar l'activitat.");
    }
  }

  async function assignLunchBreaks() {
    setError("");
    setSuccessMessage("");
    try {
      const response = await fetch(`${API_URL}/scheduler/lunch-breaks/assign`, { method: "POST" });
      const data = await response.json();
      if (!data.ok) {
        setError("No s'han pogut assignar les hores de dinar.");
        return;
      }
      setActivities((data.activities || []).map(normalizeTimetableActivity));
      setConflicts(data.conflicts || []);
      const addedCount = data.added?.length || 0;
      const skippedCount = data.skipped_no_slot?.length || 0;
      setSuccessMessage(
        `S'han afegit ${addedCount} hores de dinar.` +
        (skippedCount > 0 ? ` ${skippedCount} professors no tenien cap franja lliure entre les 12h i les 16h.` : "")
      );
    } catch {
      setError("No s'han pogut assignar les hores de dinar.");
    }
  }

  async function toggleGroupBreak(day) {
    if (!selectedGroup) return;
    setIsTogglingBreak(true);
    setError("");
    setSuccessMessage("");
    try {
      const response = await fetch(`${API_URL}/scheduler/breaks/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group: selectedGroup, day }),
      });
      const data = await response.json();
      if (!data.ok) {
        setError(
          data.error === "no_free_slot"
            ? "No hi ha cap franja lliure entre les 9:30 i les 12:30 per aquest grup i dia."
            : "No s'ha pogut canviar el descans."
        );
        return;
      }
      setActivities((data.activities || []).map(normalizeTimetableActivity));
      setConflicts(data.conflicts || []);
    } catch {
      setError("No s'ha pogut canviar el descans.");
    } finally {
      setIsTogglingBreak(false);
    }
  }

  async function addCoordination() {
    const teacher = window.prompt("Professor/s (separats per coma si són diversos):");
    if (!teacher) return;
    const day = window.prompt(`Dia (${DAYS.join(", ")}):`, DAYS[0]);
    if (!day || !DAYS.includes(day)) {
      setError("Dia no vàlid.");
      return;
    }
    const start = window.prompt(`Hora d'inici (${HOURS[0]} - ${HOURS[HOURS.length - 1]}):`, HOURS[0]);
    if (!start || !HOURS.includes(start)) {
      setError("Hora no vàlida.");
      return;
    }
    const durationRaw = window.prompt("Durada en blocs de 30 min (2 = 1 hora):", "2");
    const duration = parseInt(durationRaw, 10) || 2;
    await addManualActivity({ subject: "Coordinació", day, start, duration, teacher });
  }

  async function fetchSuggestions(activityId) {
    if (!proposal?.id) return;
    setSuggestionsByActivity((prev) => ({ ...prev, [activityId]: { loading: true, slots: [] } }));
    try {
      const response = await fetch(
        `${API_URL}/scheduler/proposal/${proposal.id}/activity/${activityId}/suggestions`
      );
      const data = await response.json();
      setSuggestionsByActivity((prev) => ({
        ...prev,
        [activityId]: { loading: false, slots: data.suggested_slots || [] },
      }));
    } catch (err) {
      setSuggestionsByActivity((prev) => ({ ...prev, [activityId]: { loading: false, slots: [] } }));
    }
  }

  async function moveActivity(activityId, day, start) {
    const prevActivities = activities ? activities.slice() : [];
    const prevConflicts = conflicts ? conflicts.slice() : [];
    const prevSelectedActivityId = selectedActivityId;
    setIsSaving(true);
    setError("");
    setSuccessMessage("");

    try {
      const targetUrl = proposal?.id
        ? `${API_URL}/scheduler/proposal/${proposal.id}/move`
        : `${API_URL}/scheduler/move`;

      const response = await fetch(targetUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          activity_id: activityId,
          day,
          start,
        }),
      });

      const data = await response.json();
      console.log("MOVE RESPONSE", data);

      const rawConflicts = data.conflicts || data.proposal?.conflicts || [];
      const relatedConflicts = (rawConflicts || []).filter((conf) => {
        const ids = conf.activities || conf.data?.activities || [];
        return ids.includes(activityId);
      });
      if (!response.ok || data.ok !== true) {
        setActivities(prevActivities);
        setConflicts(prevConflicts);
        setSelectedActivityId(prevSelectedActivityId);
        setError(data.error === "validation_failed" ? "El moviment no és vàlid." : "No s'ha pogut moure l'activitat.");
        return;
      }

      setSuccessMessage("Moviment desat.");
      const nextActivities = (data.activities || data.proposal?.activities || []).map(normalizeTimetableActivity);

      if (data.proposal) {
        setProposal(data.proposal);
        setGeneratedUnscheduledActivities(data.unscheduled_activities || []);
        setGenerationStats((current) => current ? {
          ...current,
          unscheduled_activities_total: (data.unscheduled_activities || []).length,
        } : current);
      }

      setActivities(nextActivities);
      setConflicts(rawConflicts);
      setSelectedActivityId(null);
    } catch (err) {
      setActivities(prevActivities);
      setConflicts(prevConflicts);
      setSelectedActivityId(prevSelectedActivityId);
      setError("No s'ha pogut desar el moviment.");
    } finally {
      setIsSaving(false);
      setDraggedActivityId(null);
      setDropTarget(null);
    }
  }

  async function undoLastMove() {
    if (!proposal?.id) return;
    setIsSaving(true);
    setError("");
    setSuccessMessage("");
    try {
      const response = await fetch(`${API_URL}/scheduler/proposal/${proposal.id}/undo`, {
        method: "POST",
      });
      const data = await response.json();

      if (!response.ok || data.ok !== true) {
        setError(data.error === "nothing_to_undo" ? "No hi ha res per desfer." : "No s'ha pogut desfer el moviment.");
        return;
      }

      setSuccessMessage("Últim moviment desfet.");
      const nextActivities = (data.proposal?.activities || []).map(normalizeTimetableActivity);
      setProposal(data.proposal);
      setActivities(nextActivities);
      setConflicts(data.proposal?.conflicts || []);
      setGeneratedUnscheduledActivities(data.unscheduled_activities || []);
      setSelectedActivityId(null);
    } catch (err) {
      setError("No s'ha pogut desfer el moviment.");
    } finally {
      setIsSaving(false);
    }
  }

  async function redoLastMove() {
    if (!proposal?.id) return;
    setIsSaving(true);
    setError("");
    setSuccessMessage("");
    try {
      const response = await fetch(`${API_URL}/scheduler/proposal/${proposal.id}/redo`, {
        method: "POST",
      });
      const data = await response.json();

      if (!response.ok || data.ok !== true) {
        setError(data.error === "nothing_to_redo" ? "No hi ha res per refer." : "No s'ha pogut refer el moviment.");
        return;
      }

      setSuccessMessage("Moviment refet.");
      const nextActivities = (data.proposal?.activities || []).map(normalizeTimetableActivity);
      setProposal(data.proposal);
      setActivities(nextActivities);
      setConflicts(data.proposal?.conflicts || []);
      setGeneratedUnscheduledActivities(data.unscheduled_activities || []);
      setSelectedActivityId(null);
    } catch (err) {
      setError("No s'ha pogut refer el moviment.");
    } finally {
      setIsSaving(false);
    }
  }

  function handleDragStart(event, activityId) {
    if (event?.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(activityId));
    }
    setDraggedActivityId(activityId);
  }

  function getDraggedActivityId(event) {
    const dataId = event?.dataTransfer?.getData("text/plain");
    if (dataId) {
      const parsed = Number(dataId);
      return Number.isNaN(parsed) ? null : parsed;
    }

    // fallback: some browsers/environments may lose dataTransfer during drag
    return draggedActivityId || null;
  }

  function getQuarterSuffix(value) {
    const text = String(value || "").trim();
    const match = text.match(/(?:\s|^)(1Q|2Q)$/i);
    return match ? match[1].toUpperCase() : null;
  }

  function canShareSlotWithQuarter(existingActivity, candidateActivity) {
    if (!existingActivity || !candidateActivity) {
      return false;
    }

    if (getGroupParentName(existingActivity.group) !== getGroupParentName(candidateActivity.group)) {
      return false;
    }

    // Consider subject suffixes first, then group suffixes (match backend logic)
    const existingSuffix = getQuarterSuffix(existingActivity.subject) || getQuarterSuffix(existingActivity.group);
    const candidateSuffix = getQuarterSuffix(candidateActivity.subject) || getQuarterSuffix(candidateActivity.group);

    return existingSuffix && candidateSuffix && existingSuffix !== candidateSuffix;
  }

  function canMoveActivityToSlot(activityId, day, start) {
    // find candidate in active activities or in unscheduled/generated lists
    const activity = activities.find((item) => item.id === activityId)
      || generatedUnscheduledActivities.find((item) => item.id === activityId)
      || unscheduledActivities.find((item) => item.id === activityId);
    if (!activity) {
      return true;
    }

    // build the slot activities from the full `activities` list (not the filtered view)
    const slotActivities = (activities || []).filter(
      (a) => String(a.day) === String(day) && String(a.start) === String(start)
    );
    const sameGroupActivities = slotActivities.filter(
      (item) => getGroupParentName(item.group) === getGroupParentName(activity.group)
    );

    if (!sameGroupActivities.length) {
      return true;
    }

    if (sameGroupActivities.length > 1) {
      const message = "Hi ha més d'una activitat en aquesta franja per al mateix grup.";
      setError(message);
      return false;
    }

    const existing = sameGroupActivities[0];
    if (existing.id === activityId) {
      return true;
    }

    if (canShareSlotWithQuarter(existing, activity)) {
      return true;
    }

    const message = "No es pot col·locar una altra assignatura diferent en aquesta franja per al mateix grup.";
    setError(message);
    alert(message);
    return false;
  }

  async function loadActivityExplanation(activityId) {
    setIsLoadingExplanation(true);
    setExplanationError("");

    try {
      const response = await fetch(`${API_URL}/schedule/activity/${activityId}/explanation`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "No s'ha pogut carregar l'explicació.");
      }

      setSelectedExplanation(data);
      setSelectedActivityId(activityId);
    } catch (err) {
      setSelectedExplanation(null);
      setExplanationError(err.message || "No s'ha pogut carregar l'explicació.");
    } finally {
      setIsLoadingExplanation(false);
    }
  }

  function handleDragOver(event, day, start) {
    event.preventDefault();
    setDropTarget(`${day}-${start}`);
  }

  function handleDrop(event, day, start) {
    event.preventDefault();

    // Prefer dataTransfer id but fallback to draggedActivityId state
    const transferId = event?.dataTransfer?.getData("text/plain");
    let activityId = null;
    if (transferId) {
      const parsed = Number(transferId);
      activityId = Number.isNaN(parsed) ? null : parsed;
    }

    if (activityId === null) {
      // fallback to React state if transfer data missing
      activityId = draggedActivityId || null;
    }

    if (activityId === null || Number.isNaN(activityId)) {
      // nothing to do; clear transient highlights
      setDropTarget(null);
      setDraggedActivityId(null);
      return;
    }

    // client-side validation: prevent different subjects in same slot for same parent-group
    if (!canMoveActivityToSlot(activityId, day, start)) {
      // clear transient highlights and keep state consistent
      setDropTarget(null);
      setDraggedActivityId(null);
      return;
    }

    // passed client-side validation -> perform server move
    moveActivity(activityId, day, start);
  }

  function renderActivity(activity) {
    const hasConflict = conflictIds.has(activity.id);
    const conflictReasons = conflictMessages.get(activity.id) || [];
    const isSelected = selectedActivityId === activity.id;
    const normalizedSubject = (activity.subject || "").trim().toLowerCase();
    const isBreakOrCoordination = normalizedSubject === "descans" || normalizedSubject === "coordinació" || normalizedSubject === "coordinacio";
    const groupColor = !hasConflict && !isBreakOrCoordination ? getGroupColor(activity.group) : null;

    return (
      <article
        key={activity.id}
        className={[
          "activity-card",
          hasConflict ? "activity-card--conflict" : "",
          isSelected ? "activity-card--selected" : "",
          isBreakOrCoordination ? "activity-card--break" : "",
        ].filter(Boolean).join(" ")}
        draggable
        title={hasConflict ? conflictReasons.join("\n") : undefined}
        style={groupColor ? { background: groupColor.background, borderColor: groupColor.border } : undefined}
        onClick={() => setSelectedActivityId(activity.id)}
        onDragStart={(event) => handleDragStart(event, activity.id)}
        onDragEnd={() => {
          setDraggedActivityId(null);
          setDropTarget(null);
        }}
      >
        <strong>{activity.subject}</strong>
        <span>{activity.teacher}</span>
        <small>
          {activity.group}
          {activity.room ? ` · ${activity.room}` : ""}
        </small>
        {hasConflict && conflictReasons.length > 0 ? (
          <small className="activity-conflict-reason">⚠️ {conflictReasons[0]}</small>
        ) : null}
        <div style={{ display: "flex", gap: 4 }}>
          <button
            type="button"
            className="activity-info-button"
            onMouseDown={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              loadActivityExplanation(activity.id);
            }}
          >
            Info
          </button>
          {isBreakOrCoordination ? (
            <button
              type="button"
              className="activity-info-button"
              onMouseDown={(event) => {
                event.preventDefault();
                event.stopPropagation();
              }}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                deleteActivity(activity.id);
              }}
            >
              Elimina
            </button>
          ) : null}
        </div>
      </article>
    );
  }

  function updateAvailabilitySelection(slotKey, event, draft, setDraft, field = "preferred_availability", anchor = availabilitySelectionAnchor, setAnchor = setAvailabilitySelectionAnchor) {
    event.preventDefault();
    event.stopPropagation();

    const currentSlots = new Set(draft[field] || []);
    if (event.shiftKey && anchor) {
      getAvailabilitySelectionRange(anchor, slotKey).forEach((slot) => currentSlots.add(slot));
    } else {
      if (currentSlots.has(slotKey)) {
        currentSlots.delete(slotKey);
      } else {
        currentSlots.add(slotKey);
      }
      setAnchor(slotKey);
    }

    setDraft({
      ...draft,
      [field]: Array.from(currentSlots).sort(),
    });
  }

  function applyAvailabilityPreset(preset, draft, setDraft, field = "preferred_availability", setAnchor = setAvailabilitySelectionAnchor) {
    const slotKeys = DAYS.flatMap((day) => HOURS.map((hour) => `${day}-${hour}`));
    const presetSlots = (() => {
      if (preset === "matí") {
        return slotKeys.filter((slotKey) => HOURS.indexOf(slotKey.split("-")[1]) < 8);
      }
      if (preset === "tarda") {
        return slotKeys.filter((slotKey) => HOURS.indexOf(slotKey.split("-")[1]) >= 8);
      }
      if (preset === "dia-complet") {
        return slotKeys;
      }
      return [];
    })();

    setDraft({
      ...draft,
      [field]: presetSlots,
    });
    setAnchor(null);
  }

  function clearAvailabilitySelection(draft, setDraft, field = "preferred_availability", setAnchor = setAvailabilitySelectionAnchor) {
    setDraft({
      ...draft,
      [field]: [],
    });
    setAnchor(null);
  }

  // Fase 1 (edició web de dades acadèmiques): botons ràpids que marquen en
  // bloc franges com a "no disponibles", reutilitzant la graella clicable
  // que ja existeix. No cal cap canvi al motor: segueix sent la mateixa
  // llista `unavailable_slots` que ja consumeix el generador.
  function applyUnavailablePreset(preset, draft, setDraft, field = "unavailable_slots", setAnchor = setUnavailableSelectionAnchor) {
    const hourIndex = (hour) => HOURS.indexOf(hour);
    const matchers = {
      "no-abans-10": (hour) => hourIndex(hour) < hourIndex("10:00"),
      "no-abans-15": (hour) => hourIndex(hour) < hourIndex("15:00"),
      "no-despres-17": (hour) => hourIndex(hour) >= hourIndex("17:00"),
      "entre-10-14": (hour) => hourIndex(hour) >= hourIndex("10:00") && hourIndex(hour) < hourIndex("14:00"),
      "nomes-matins": (hour) => hourIndex(hour) >= 8,
      "nomes-tardes": (hour) => hourIndex(hour) < 8,
    };
    const matcher = matchers[preset];
    if (!matcher) return;

    const currentSlots = new Set(draft[field] || []);
    DAYS.forEach((day) => {
      HOURS.forEach((hour) => {
        if (matcher(hour)) {
          currentSlots.add(`${day}-${hour}`);
        }
      });
    });

    setDraft({ ...draft, [field]: Array.from(currentSlots).sort() });
    setAnchor(null);
  }

  function getCurrentEntityOptions() {
    if (timetableView === "teacher") {
      return teachers;
    }
    if (timetableView === "group") {
      return groups;
    }
    if (timetableView === "room") {
      return rooms;
    }
    return [];
  }

  function getEntityLabel() {
    if (timetableView === "teacher") return "Professor";
    if (timetableView === "group") return "Grup";
    if (timetableView === "room") return "Aula";
    return "Entitat";
  }

  // Generic API helpers for academic CRUD
  async function apiJson(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(`${API_URL}${path}`, opts);
    const data = await resp.json().catch(() => ({}));
    return { ok: resp.ok, status: resp.status, data };
  }

  async function createTeacher(payload) {
    return apiJson("POST", "/academic-data/teachers", payload);
  }

  async function updateTeacher(name, payload) {
    return apiJson("PATCH", `/academic-data/teachers/${encodeURIComponent(name)}`, payload);
  }

  async function deleteTeacher(name) {
    return apiJson("DELETE", `/academic-data/teachers/${encodeURIComponent(name)}`);
  }

  async function refreshAcademicLists() {
    await loadAcademicSummary();
    await loadTimetableEntities();
  }

  // Fase 2: taula editable tipus Excel per a Assignatures. Reutilitza
  // exactament els mateixos endpoints CRUD que ja fa servir la vista
  // clàssica (/academic-data/assignments, /academic-data/subjects) — cap
  // canvi al backend ni al model de dades.
  function openSpreadsheetView() {
    const rows = teachingAssignments.map((a) => ({
      id: a.id,
      teacher: a.teacher || "",
      subject: a.subject || "",
      group: a.group || "",
      weekly_hours: typeof a.weekly_hours === "number" ? a.weekly_hours : parseFloat(a.weekly_hours) || 0,
      preferred_room: a.preferred_room || "",
      max_session_days: a.max_session_days || "",
      fixed_day: a.fixed_day || "",
      fixed_start: a.fixed_start || "",
      consecutive_group: a.consecutive_group || "",
      notes: a.notes || "",
    }));
    setSpreadsheetRows(rows);
    setSpreadsheetOriginalRows(rows);
    setUseSpreadsheetView(true);
  }

  async function saveSpreadsheetRows() {
    setIsSavingSpreadsheet(true);
    setError("");
    setSuccessMessage("");
    try {
      const originalById = new Map(spreadsheetOriginalRows.filter((r) => r.id).map((r) => [r.id, r]));
      const currentIds = new Set(spreadsheetRows.filter((r) => r.id).map((r) => r.id));

      // Files noves: sense id, i amb almenys assignatura+grup+professor omplerts.
      const newRows = spreadsheetRows.filter(
        (r) => !r.id && (r.subject || r.teacher || r.group)
      );

      // Files modificades: id existent i algun camp diferent de l'original.
      const changedRows = spreadsheetRows.filter((r) => {
        if (!r.id) return false;
        const original = originalById.get(r.id);
        if (!original) return false;
        return ASSIGNMENT_SHEET_COLUMNS.some((col) => (original[col.id] ?? "") !== (r[col.id] ?? ""));
      });

      // Files esborrades: eren a l'original i ja no hi són a la taula actual.
      const deletedIds = spreadsheetOriginalRows.filter((r) => r.id && !currentIds.has(r.id)).map((r) => r.id);

      const existingSubjectNames = new Set(academicSubjects.map((s) => s.name));
      const errors = [];

      async function ensureSubjectExists(subjectName) {
        if (!subjectName || existingSubjectNames.has(subjectName)) return;
        const res = await apiJson("POST", "/academic-data/subjects", { name: subjectName });
        if (res.ok) {
          existingSubjectNames.add(subjectName);
        }
      }

      for (const row of newRows) {
        await ensureSubjectExists(row.subject);
        const res = await apiJson("POST", "/academic-data/assignments", {
          teacher: row.teacher,
          subject: row.subject,
          group: row.group,
          weekly_hours: row.weekly_hours,
          preferred_room: row.preferred_room,
          notes: row.notes,
          fixed_day: row.fixed_day,
          fixed_start: row.fixed_start,
          max_session_days: row.max_session_days,
          consecutive_group: row.consecutive_group,
        });
        if (!res.ok) errors.push(`${row.subject || "(nova fila)"}: ${res.data?.detail || "error en crear"}`);
      }

      for (const row of changedRows) {
        await ensureSubjectExists(row.subject);
        const res = await apiJson("PATCH", `/academic-data/assignments/${encodeURIComponent(row.id)}`, {
          teacher: row.teacher,
          subject: row.subject,
          group: row.group,
          weekly_hours: row.weekly_hours,
          preferred_room: row.preferred_room,
          notes: row.notes,
          fixed_day: row.fixed_day,
          fixed_start: row.fixed_start,
          max_session_days: row.max_session_days,
          consecutive_group: row.consecutive_group,
        });
        if (!res.ok) errors.push(`${row.subject || row.id}: ${res.data?.detail || "error en desar"}`);
      }

      for (const id of deletedIds) {
        const res = await apiJson("DELETE", `/academic-data/assignments/${encodeURIComponent(id)}`);
        if (!res.ok) errors.push(`Esborrar ${id}: ${res.data?.detail || "error"}`);
      }

      await refreshAcademicLists();

      if (errors.length > 0) {
        setError(`Alguns canvis no s'han pogut desar: ${errors.join(" · ")}`);
      } else {
        setSuccessMessage(
          `Desat: ${newRows.length} noves, ${changedRows.length} modificades, ${deletedIds.length} esborrades.`
        );
        setUseSpreadsheetView(false);
      }
    } catch (err) {
      setError("No s'han pogut desar tots els canvis de la taula.");
    } finally {
      setIsSavingSpreadsheet(false);
    }
  }

  // More CRUD helpers
  async function createGroup(payload) {
    return apiJson("POST", "/academic-data/groups", payload);
  }
  async function updateGroup(name, payload) {
    return apiJson("PATCH", `/academic-data/groups/${encodeURIComponent(name)}`, payload);
  }
  async function deleteGroup(name) {
    return apiJson("DELETE", `/academic-data/groups/${encodeURIComponent(name)}`);
  }

  async function createSubject(payload) {
    return apiJson("POST", "/academic-data/subjects", payload);
  }
  async function updateSubject(name, payload) {
    return apiJson("PATCH", `/academic-data/subjects/${encodeURIComponent(name)}`, payload);
  }
  async function deleteSubject(name) {
    return apiJson("DELETE", `/academic-data/subjects/${encodeURIComponent(name)}`);
  }

  async function createRoom(payload) {
    return apiJson("POST", "/academic-data/rooms", payload);
  }
  async function updateRoom(name, payload) {
    return apiJson("PATCH", `/academic-data/rooms/${encodeURIComponent(name)}`, payload);
  }
  async function deleteRoom(name) {
    return apiJson("DELETE", `/academic-data/rooms/${encodeURIComponent(name)}`);
  }

  async function createAssignment(payload) {
    return apiJson("POST", "/academic-data/assignments", payload);
  }
  async function updateAssignment(id, payload) {
    return apiJson("PATCH", `/academic-data/assignments/${encodeURIComponent(id)}`, payload);
  }
  async function deleteAssignment(id) {
    return apiJson("DELETE", `/academic-data/assignments/${encodeURIComponent(id)}`);
  }

  async function mergeQuarterAssignments(firstId, secondId) {
    return apiJson("POST", "/academic-data/assignments/merge-quarters", {
      first_id: firstId,
      second_id: secondId,
    });
  }

  async function splitMergedAssignment(id) {
    return apiJson("POST", `/academic-data/assignments/${encodeURIComponent(id)}/split`);
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <img className="brand-logo" src="/logo-emad.png" alt="Logo EMAD" />
          <div>
            <h1>EMAD · Planificació d'Horaris</h1>
            <p>
              {filteredActivities.length} activitats visibles · {conflicts.length} conflictes
            </p>
          </div>
        </div>

        <div className="topbar-actions">
          <div className="view-switch">
            <button onClick={() => setCurrentScreen("timetable")} className={currentScreen === "timetable" ? "active" : ""}>Horari</button>
            <button onClick={() => setCurrentScreen("academic")} className={currentScreen === "academic" ? "active" : ""}>Dades acadèmiques</button>
          </div>
          <input
            ref={workbookInputRef}
            type="file"
            accept=".xlsx"
            multiple
            style={{ display: "none" }}
            onChange={importAcademicWorkbook}
          />

          <input
            ref={academicSpreadsheetInputRef}
            type="file"
            accept=".xlsx"
            style={{ display: "none" }}
            onChange={onAcademicSpreadsheetSelected}
          />

          <input
            ref={fetInputRef}
            type="file"
            accept=".fet"
            style={{ display: "none" }}
            onChange={onFetFileSelected}
          />

          <button type="button" onClick={generateProposal} disabled={isLoading || isSaving || isGenerating}>
            {isGenerating ? "Generant..." : "Genera proposta"}
          </button>

          <button
            type="button"
            onClick={undoLastMove}
            disabled={isLoading || isSaving || isGenerating || !proposal?.id}
            title="Desfer l'últim moviment o intercanvi d'activitats"
          >
            ↩️ Desfer
          </button>

          <button
            type="button"
            onClick={redoLastMove}
            disabled={isLoading || isSaving || isGenerating || !proposal?.id}
            title="Refer el moviment desfet"
          >
            ↪️ Refer
          </button>

          <button type="button" onClick={openFetSelector} disabled={isLoading || isSaving || isGenerating}>
            Carrega FET
          </button>

          <button
            type="button"
            onClick={downloadBlankSpreadsheet}
            disabled={isLoading || isSaving || isGenerating}
            title="Descarrega un full de càlcul model, buit, per introduir les dades des de zero"
            style={{ marginLeft: 8 }}
          >
            📥 Model buit (Excel)
          </button>

          <button
            type="button"
            onClick={downloadCurrentSpreadsheet}
            disabled={isLoading || isSaving || isGenerating}
            title="Descarrega un full de càlcul amb totes les dades acadèmiques actuals"
            style={{ marginLeft: 8 }}
          >
            📥 Dades actuals (Excel)
          </button>

          <button
            type="button"
            onClick={() => academicSpreadsheetInputRef.current?.click()}
            disabled={isLoading || isSaving || isGenerating || isImportingSpreadsheet}
            title="Puja un full de càlcul (model omplert) per substituir professors, grups, assignatures i aules"
            style={{ marginLeft: 8 }}
          >
            {isImportingSpreadsheet ? "Important..." : "📤 Importa Excel"}
          </button>

          {selectedGroup ? (
            <div style={{ display: "flex", gap: 3, alignItems: "center", marginLeft: 8 }}>
              <span style={{ fontSize: 12, color: "#667085" }}>Descans:</span>
              {DAYS.map((day) => {
                const isActive = groupBreakDays.has(day);
                return (
                  <button
                    key={day}
                    type="button"
                    onClick={() => toggleGroupBreak(day)}
                    disabled={isLoading || isSaving || isGenerating || isTogglingBreak}
                    title={`Descans ${day} per ${selectedGroup} (entre les 9:30 i les 12:30)`}
                    style={{
                      padding: "0 6px",
                      background: isActive ? "#2f6f73" : "#ffffff",
                      color: isActive ? "#ffffff" : "#1f2937",
                    }}
                  >
                    {day.slice(0, 3)}
                  </button>
                );
              })}
            </div>
          ) : null}

          <button
            type="button"
            onClick={addCoordination}
            disabled={isLoading || isSaving || isGenerating}
            title="Afegeix una hora de coordinació per a un o més professors"
            style={{ marginLeft: 8 }}
          >
            + Coordinació
          </button>

          <button
            type="button"
            onClick={assignLunchBreaks}
            disabled={isLoading || isSaving || isGenerating}
            title="Assigna una hora de dinar (12h-16h) als professors amb classe matí i tarda"
            style={{ marginLeft: 8 }}
          >
            + Dinars
          </button>

          <button type="button" onClick={loadData} disabled={isLoading || isSaving || isGenerating}>
            {isLoading ? "Carregant" : "Actualitza"}
          </button>
        </div>
      </header>

      {error && <div className="notice notice--error">{error}</div>}
      {successMessage && <div className="notice notice--success">{successMessage}</div>}
      {isSaving && <div className="notice">Desant moviment</div>}

      {selectedActivityId !== null && (
        <div className="notice">Activitat seleccionada: {selectedActivityId}</div>
      )}

      {currentScreen === "academic" && (
        <section className="academic-layout">
          <div className="academic-top">
            <button onClick={() => setAcademicTab("teachers")} className={academicTab === "teachers" ? "active" : ""}>Professors</button>
            <button onClick={() => setAcademicTab("groups")} className={academicTab === "groups" ? "active" : ""}>Grups d'alumnes</button>
            <button onClick={() => setAcademicTab("subjects")} className={academicTab === "subjects" ? "active" : ""}>Assignatures</button>
            <button onClick={() => setAcademicTab("rooms")} className={academicTab === "rooms" ? "active" : ""}>Aules</button>
            <button onClick={() => setAcademicTab("assignments")} className={academicTab === "assignments" ? "active" : ""}>Assignacions docents</button>
            <button style={{ marginLeft: 16 }} onClick={() => refreshAcademicLists()}>Actualitza</button>
          </div>

          <div className="academic-content">
            {academicTab === "teachers" && (
              <div className="teachers-layout">
                <div className="teachers-list">
                <h2>Professors</h2>
                <table className="academic-table">
                  <thead>
                    <tr>
                      <th>Nom</th>
                      <th>Nom curt</th>
                      <th>Actiu</th>
                      <th>Restriccions</th>
                      <th>Accions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {teachers.map((t) => {
                      const restriction = teacherRestrictions.find((item) => item.teacher === t.name);
                      const manualCount = (restriction?.unavailable_slots || []).length;
                      const fetCount = (restriction?.fet_unavailable_slots || []).length;
                      return (
                      <tr key={t.name}>
                        <td>
                          {teacherEdit === t.name ? (
                            <input
                              value={teacherEditValues.name}
                              onChange={(event) => setTeacherEditValues({ ...teacherEditValues, name: event.target.value })}
                            />
                          ) : (
                            t.name
                          )}
                        </td>
                        <td>
                          {teacherEdit === t.name ? (
                            <input
                              value={teacherEditValues.short_name}
                              onChange={(event) => setTeacherEditValues({ ...teacherEditValues, short_name: event.target.value })}
                            />
                          ) : (
                            t.short_name || "-"
                          )}
                        </td>
                        <td>
                          {teacherEdit === t.name ? (
                            <input
                              type="checkbox"
                              checked={teacherEditValues.active}
                              onChange={(event) => setTeacherEditValues({ ...teacherEditValues, active: event.target.checked })}
                            />
                          ) : (
                            t.active !== false ? "Sí" : "No"
                          )}
                        </td>
                        <td>
                          {restriction ? (
                            <span title="Franges no disponibles marcades manualment + les que vénen del FET">
                              {manualCount} manuals · {fetCount} del FET
                            </span>
                          ) : (
                            <span className="muted">{fetCount} del FET</span>
                          )}
                          {" "}
                          <button
                            type="button"
                            className={teacherRestrictionEditor === t.name ? "active" : ""}
                            onClick={() => openTeacherRestrictionEditor(teacherRestrictionEditor === t.name ? "" : t.name)}
                          >
                            {teacherRestrictionEditor === t.name ? "Editant…" : "Hores / restriccions"}
                          </button>
                        </td>
                        <td>
                          {teacherEdit === t.name ? (
                            <>
                              <button onClick={async () => {
                                const payload = {
                                  name: teacherEditValues.name,
                                  short_name: teacherEditValues.short_name,
                                  active: teacherEditValues.active,
                                };
                                const res = await updateTeacher(t.name, payload);
                                if (res.ok) {
                                  setTeacherEdit(null);
                                  await refreshAcademicLists();
                                } else {
                                  alert("No s'ha pogut actualitzar el professor.");
                                }
                              }}>Desa</button>
                              <button onClick={() => setTeacherEdit(null)}>Cancel·la</button>
                            </>
                          ) : (
                            <>
                              <button onClick={() => {
                                setTeacherEdit(t.name);
                                setTeacherEditValues({ name: t.name, short_name: t.short_name || "", active: t.active !== false });
                              }}>Edita</button>
                              <button onClick={async () => {
                                const res = await deleteTeacher(t.name);
                                if (res.ok) await refreshAcademicLists(); else alert("No s'ha pogut eliminar el professor.");
                              }}>Elimina</button>
                            </>
                          )}
                        </td>
                      </tr>
                      );
                    })}
                    <tr>
                      <td>
                        <input
                          value={teacherDraft.name}
                          placeholder="Nom"
                          onChange={(event) => setTeacherDraft({ ...teacherDraft, name: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          value={teacherDraft.short_name}
                          placeholder="Nom curt"
                          onChange={(event) => setTeacherDraft({ ...teacherDraft, short_name: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          checked={teacherDraft.active}
                          onChange={(event) => setTeacherDraft({ ...teacherDraft, active: event.target.checked })}
                        />
                      </td>
                      <td>
                        <button onClick={async () => {
                          if (!teacherDraft.name) {
                            alert("El nom del professor és obligatori");
                            return;
                          }
                          const res = await createTeacher(teacherDraft);
                          if (res.ok) {
                            setTeacherDraft({ name: "", short_name: "", active: true });
                            await refreshAcademicLists();
                          } else {
                            alert("No s'ha pogut crear el professor.");
                          }
                        }}>Afegeix</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
                </div>
                <div className="teachers-restrictions-panel">
                  <h2>Hores disponibles i restriccions</h2>
                  {renderTeacherRestrictionEditor()}
                </div>
              </div>
            )}

            {academicTab === "groups" && (
              <div>
                <h2>Grups d'alumnes</h2>
                <table className="academic-table">
                  <thead>
                    <tr>
                      <th>Nom</th>
                      <th>Curs</th>
                      <th>Actiu</th>
                      <th>Accions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((g) => (
                      <tr key={g.name}>
                        <td>
                          {groupEdit === g.name ? (
                            <input
                              value={groupEditValues.name}
                              onChange={(event) => setGroupEditValues({ ...groupEditValues, name: event.target.value })}
                            />
                          ) : (
                            g.name
                          )}
                        </td>
                        <td>
                          {groupEdit === g.name ? (
                            <input
                              value={groupEditValues.course}
                              onChange={(event) => setGroupEditValues({ ...groupEditValues, course: event.target.value })}
                            />
                          ) : (
                            g.course || "-"
                          )}
                        </td>
                        <td>
                          {groupEdit === g.name ? (
                            <input
                              type="checkbox"
                              checked={groupEditValues.active}
                              onChange={(event) => setGroupEditValues({ ...groupEditValues, active: event.target.checked })}
                            />
                          ) : (
                            g.active !== false ? "Sí" : "No"
                          )}
                        </td>
                        <td>
                          {groupEdit === g.name ? (
                            <>
                              <button onClick={async () => {
                                const payload = {
                                  name: groupEditValues.name,
                                  course: groupEditValues.course,
                                  active: groupEditValues.active,
                                };
                                const res = await updateGroup(g.name, payload);
                                if (res.ok) {
                                  setGroupEdit(null);
                                  await refreshAcademicLists();
                                } else {
                                  alert("No s'ha pogut actualitzar el grup.");
                                }
                              }}>Desa</button>
                              <button onClick={() => setGroupEdit(null)}>Cancel·la</button>
                            </>
                          ) : (
                            <>
                              <button onClick={() => {
                                setGroupEdit(g.name);
                                setGroupEditValues({ name: g.name, course: g.course || "", active: g.active !== false });
                              }}>Edita</button>
                              <button onClick={async () => {
                                const res = await deleteGroup(g.name);
                                if (res.ok) await refreshAcademicLists(); else alert("No s'ha pogut eliminar el grup.");
                              }}>Elimina</button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                    <tr>
                      <td>
                        <input
                          value={groupDraft.name}
                          placeholder="Nom"
                          onChange={(event) => setGroupDraft({ ...groupDraft, name: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          value={groupDraft.course}
                          placeholder="Curs"
                          onChange={(event) => setGroupDraft({ ...groupDraft, course: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          type="checkbox"
                          checked={groupDraft.active}
                          onChange={(event) => setGroupDraft({ ...groupDraft, active: event.target.checked })}
                        />
                      </td>
                      <td>
                        <button onClick={async () => {
                          if (!groupDraft.name) {
                            alert("El nom del grup és obligatori");
                            return;
                          }
                          const res = await createGroup(groupDraft);
                          if (res.ok) {
                            setGroupDraft({ name: "", course: "", active: true });
                            await refreshAcademicLists();
                          } else {
                            alert("No s'ha pogut crear el grup.");
                          }
                        }}>Afegeix</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            {academicTab === "subjects" && (
              <div>
                <h2>Assignatures</h2>
                <table className="academic-table">
                  <thead>
                    <tr>
                      <th>Nom</th>
                      <th>Hores setmanals</th>
                      <th>Durades de sessió permeses</th>
                      <th>Accions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {academicSubjects.map((s) => (
                      <tr key={s.name}>
                        <td>
                          {subjectEdit === s.name ? (
                            <input
                              value={subjectEditValues.name}
                              onChange={(event) => setSubjectEditValues({ ...subjectEditValues, name: event.target.value })}
                            />
                          ) : (
                            s.name
                          )}
                        </td>
                        <td>
                          {subjectEdit === s.name ? (
                            <input
                              type="number"
                              step="0.5"
                              value={subjectEditValues.weekly_hours}
                              onChange={(event) => setSubjectEditValues({ ...subjectEditValues, weekly_hours: event.target.value })}
                            />
                          ) : (
                            s.weekly_hours || "-"
                          )}
                        </td>
                        <td>
                          {subjectEdit === s.name ? (
                            <input
                              value={subjectEditValues.allowed_session_lengths}
                              onChange={(event) => setSubjectEditValues({ ...subjectEditValues, allowed_session_lengths: event.target.value })}
                            />
                          ) : (
                            formatSessionLengths(s.allowed_session_lengths)
                          )}
                        </td>
                        <td>
                          {subjectEdit === s.name ? (
                            <>
                              <button onClick={async () => {
                                const payload = {
                                  name: subjectEditValues.name,
                                  weekly_hours: parseFloat(subjectEditValues.weekly_hours) || 0,
                                  allowed_session_lengths: parseSessionLengths(subjectEditValues.allowed_session_lengths),
                                };
                                const res = await updateSubject(s.name, payload);
                                if (res.ok) {
                                  setSubjectEdit(null);
                                  await refreshAcademicLists();
                                } else {
                                  alert("No s'ha pogut actualitzar l'assignatura.");
                                }
                              }}>Desa</button>
                              <button onClick={() => setSubjectEdit(null)}>Cancel·la</button>
                            </>
                          ) : (
                            <>
                              <button onClick={() => {
                                setSubjectEdit(s.name);
                                setSubjectEditValues({
                                  name: s.name,
                                  weekly_hours: s.weekly_hours || "",
                                  allowed_session_lengths: formatSessionLengths(s.allowed_session_lengths),
                                });
                              }}>Edita</button>
                              <button onClick={async () => {
                                const res = await deleteSubject(s.name);
                                if (res.ok) await refreshAcademicLists(); else alert("No s'ha pogut eliminar l'assignatura.");
                              }}>Elimina</button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                    <tr>
                      <td>
                        <input
                          value={subjectDraft.name}
                          placeholder="Nom"
                          onChange={(event) => setSubjectDraft({ ...subjectDraft, name: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.5"
                          value={subjectDraft.weekly_hours}
                          placeholder="Setmanals"
                          onChange={(event) => setSubjectDraft({ ...subjectDraft, weekly_hours: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          value={subjectDraft.allowed_session_lengths}
                          placeholder="2+3"
                          onChange={(event) => setSubjectDraft({ ...subjectDraft, allowed_session_lengths: event.target.value })}
                        />
                      </td>
                      <td>
                        <button onClick={async () => {
                          if (!subjectDraft.name) {
                            alert("El nom de l'assignatura és obligatori");
                            return;
                          }
                          const payload = {
                            name: subjectDraft.name,
                            weekly_hours: parseFloat(subjectDraft.weekly_hours) || 0,
                          };
                          const res = await createSubject(payload);
                          if (res.ok) {
                            setSubjectDraft({ name: "", weekly_hours: "", allowed_session_lengths: "" });
                            await refreshAcademicLists();
                          } else {
                            alert("No s'ha pogut crear l'assignatura.");
                          }
                        }}>Afegeix</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            {academicTab === "rooms" && (
              <div>
                <h2>Aules</h2>
                <table className="academic-table">
                  <thead>
                    <tr>
                      <th>Nom</th>
                      <th>Capacitat</th>
                      <th>Accions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rooms.map((r) => (
                      <tr key={r.name}>
                        <td>
                          {roomEdit === r.name ? (
                            <input
                              value={roomEditValues.name}
                              onChange={(event) => setRoomEditValues({ ...roomEditValues, name: event.target.value })}
                            />
                          ) : (
                            r.name
                          )}
                        </td>
                        <td>
                          {roomEdit === r.name ? (
                            <input
                              type="number"
                              min="0"
                              value={roomEditValues.capacity}
                              onChange={(event) => setRoomEditValues({ ...roomEditValues, capacity: event.target.value })}
                            />
                          ) : (
                            r.capacity ?? "-"
                          )}
                        </td>
                        <td>
                          {roomEdit === r.name ? (
                            <>
                              <button onClick={async () => {
                                const payload = {
                                  name: roomEditValues.name,
                                  capacity: parseInt(roomEditValues.capacity, 10) || 0,
                                };
                                const res = await updateRoom(r.name, payload);
                                if (res.ok) {
                                  setRoomEdit(null);
                                  await refreshAcademicLists();
                                } else {
                                  alert("No s'ha pogut actualitzar l'aula.");
                                }
                              }}>Desa</button>
                              <button onClick={() => setRoomEdit(null)}>Cancel·la</button>
                            </>
                          ) : (
                            <>
                              <button onClick={() => {
                                setRoomEdit(r.name);
                                setRoomEditValues({ name: r.name, capacity: r.capacity ?? "" });
                              }}>Edita</button>
                              <button onClick={async () => {
                                const res = await deleteRoom(r.name);
                                if (res.ok) await refreshAcademicLists(); else alert("No s'ha pogut eliminar l'aula.");
                              }}>Elimina</button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                    <tr>
                      <td>
                        <input
                          value={roomDraft.name}
                          placeholder="Nom"
                          onChange={(event) => setRoomDraft({ ...roomDraft, name: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          min="0"
                          value={roomDraft.capacity}
                          placeholder="Capacitat"
                          onChange={(event) => setRoomDraft({ ...roomDraft, capacity: event.target.value })}
                        />
                      </td>
                      <td>
                        <button onClick={async () => {
                          if (!roomDraft.name) {
                            alert("El nom de l'aula és obligatori");
                            return;
                          }
                          const payload = {
                            name: roomDraft.name,
                            capacity: parseInt(roomDraft.capacity, 10) || 0,
                          };
                          const res = await createRoom(payload);
                          if (res.ok) {
                            setRoomDraft({ name: "", capacity: "" });
                            await refreshAcademicLists();
                          } else {
                            alert("No s'ha pogut crear l'aula.");
                          }
                        }}>Afegeix</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            {academicTab === "assignments" && (
              <div>
                <h2>Assignacions docents</h2>

                <div style={{ marginBottom: 12 }}>
                  {!useSpreadsheetView ? (
                    <button type="button" onClick={openSpreadsheetView}>
                      📊 Vista taula (edició ràpida tipus Excel)
                    </button>
                  ) : (
                    <button type="button" onClick={() => setUseSpreadsheetView(false)} disabled={isSavingSpreadsheet}>
                      ← Torna a la vista clàssica
                    </button>
                  )}
                </div>

                {useSpreadsheetView ? (
                  <div>
                    <div className="muted" style={{ marginBottom: 8 }}>
                      Doble clic per editar una cel·la. Navega amb el teclat. Selecciona un rang i copia/enganxa
                      amb Ctrl/Cmd+C i Ctrl/Cmd+V, també des d'Excel o Google Sheets. Afegeix files noves des del
                      final de la taula; esborra-les seleccionant-les i prement Suprimir.
                    </div>
                    <DataSheetGrid
                      value={spreadsheetRows}
                      onChange={setSpreadsheetRows}
                      columns={ASSIGNMENT_SHEET_COLUMNS}
                      height={480}
                    />
                    <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                      <button type="button" onClick={saveSpreadsheetRows} disabled={isSavingSpreadsheet}>
                        {isSavingSpreadsheet ? "Desant..." : "Desa els canvis"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setUseSpreadsheetView(false)}
                        disabled={isSavingSpreadsheet}
                      >
                        Cancel·la
                      </button>
                    </div>
                  </div>
                ) : (
                <>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8 }}>
                  <button
                    type="button"
                    disabled={selectedAssignmentIds.length !== 2}
                    onClick={async () => {
                      const res = await mergeQuarterAssignments(selectedAssignmentIds[0], selectedAssignmentIds[1]);
                      if (res.ok) {
                        setSelectedAssignmentIds([]);
                        await refreshAcademicLists();
                      } else {
                        alert(res.data?.detail || "No s'han pogut compactar les assignacions.");
                      }
                    }}
                    title="Selecciona exactament 2 assignacions del mateix grup per compactar-les en un sol bloc de 2 hores (1Q + 2Q)"
                  >
                    Compacta seleccionades (1Q + 2Q)
                  </button>
                  <span className="muted">Selecciona 2 files amb la casella per activar-ho.</span>
                </div>
                <table className="academic-table">
                  <thead>
                    <tr>
                      <th></th>
                      <th>Professor</th>
                      <th>Grup d'alumnes</th>
                      <th>Assignatura</th>
                      <th>Hores setmanals</th>
                      <th>Durades de sessió permeses</th>
                      <th>Màx. dies per repartir</th>
                      <th>Consecutiva amb (etiqueta)</th>
                      <th>Horari fix</th>
                      <th>Accions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {teachingAssignments.map((a) => (
                      <tr key={a.id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedAssignmentIds.includes(a.id)}
                            onChange={(event) => {
                              setSelectedAssignmentIds((current) =>
                                event.target.checked
                                  ? [...current, a.id].slice(-2)
                                  : current.filter((id) => id !== a.id)
                              );
                            }}
                          />
                        </td>
                        <td>
                          {assignmentEdit === a.id ? (
                            <>
                              <select
                                multiple
                                size={4}
                                value={assignmentEditValues.teacher ? assignmentEditValues.teacher.split(",").map((t) => t.trim()).filter(Boolean) : []}
                                onChange={(event) => {
                                  const selected = Array.from(event.target.selectedOptions).map((option) => option.value);
                                  setAssignmentEditValues({ ...assignmentEditValues, teacher: selected.join(", ") });
                                }}
                              >
                                {teachers.map((t) => (
                                  <option key={t.name} value={t.name}>{t.name}</option>
                                ))}
                              </select>
                              <div className="muted" style={{ fontSize: 11 }}>Ctrl/Cmd + clic per triar-ne més d'un</div>
                            </>
                          ) : (
                            a.teacher
                          )}
                        </td>
                        <td>
                          {assignmentEdit === a.id ? (
                            <select
                              value={assignmentEditValues.group}
                              onChange={(event) => setAssignmentEditValues({ ...assignmentEditValues, group: event.target.value })}
                            >
                              <option value="">Selecciona un grup</option>
                              {groups.map((g) => (
                                <option key={g.name} value={g.name}>{g.name}</option>
                              ))}
                            </select>
                          ) : (
                            a.group
                          )}
                        </td>
                        <td>
                          {assignmentEdit === a.id ? (
                            <select
                              value={assignmentEditValues.subject}
                              onChange={(event) => setAssignmentEditValues({ ...assignmentEditValues, subject: event.target.value })}
                            >
                              <option value="">Selecciona una assignatura</option>
                              {academicSubjects.map((s) => (
                                <option key={s.name} value={s.name}>{s.name}</option>
                              ))}
                            </select>
                          ) : (
                            a.subject
                          )}
                        </td>
                        <td>
                          {assignmentEdit === a.id ? (
                            <input
                              type="number"
                              step="0.5"
                              value={assignmentEditValues.weekly_hours}
                              onChange={(event) => setAssignmentEditValues({ ...assignmentEditValues, weekly_hours: event.target.value })}
                            />
                          ) : (
                            a.weekly_hours
                          )}
                        </td>
                        <td>
                          {assignmentEdit === a.id ? (
                            <input
                              value={assignmentEditValues.allowed_session_lengths}
                              placeholder="2+3"
                              title="Aquest valor pertany a l'assignatura; es desarà per a totes les assignacions que la facin servir."
                              onChange={(event) => setAssignmentEditValues({ ...assignmentEditValues, allowed_session_lengths: event.target.value })}
                            />
                          ) : (
                            formatSessionLengths(a.allowed_session_lengths)
                          )}
                        </td>
                        <td>
                          {assignmentEdit === a.id ? (
                            <input
                              type="number"
                              min="1"
                              style={{ width: 50 }}
                              value={assignmentEditValues.max_session_days}
                              onChange={(event) => setAssignmentEditValues({ ...assignmentEditValues, max_session_days: event.target.value })}
                              title="Nombre màxim de dies/sessions en què es pot repartir la durada total (mínim 1h per sessió)"
                            />
                          ) : (
                            a.max_session_days || "—"
                          )}
                        </td>
                        <td>
                          {assignmentEdit === a.id ? (
                            <input
                              type="text"
                              style={{ width: 90 }}
                              value={assignmentEditValues.consecutive_group}
                              onChange={(event) => setAssignmentEditValues({ ...assignmentEditValues, consecutive_group: event.target.value })}
                              title="Escriu la mateixa etiqueta a dues assignacions perquè el generador les col·loqui una justa darrere l'altra"
                              placeholder="p.ex. bloc1"
                            />
                          ) : (
                            a.consecutive_group || "—"
                          )}
                        </td>
                        <td>
                          {assignmentEdit === a.id ? (
                            <div style={{ display: "flex", gap: 4 }}>
                              <select
                                value={assignmentEditValues.fixed_day}
                                onChange={(event) => setAssignmentEditValues({ ...assignmentEditValues, fixed_day: event.target.value })}
                              >
                                <option value="">Sense fixar</option>
                                {DAYS.map((day) => (
                                  <option key={day} value={day}>{day}</option>
                                ))}
                              </select>
                              <select
                                value={assignmentEditValues.fixed_start}
                                onChange={(event) => setAssignmentEditValues({ ...assignmentEditValues, fixed_start: event.target.value })}
                                disabled={!assignmentEditValues.fixed_day}
                              >
                                <option value="">Hora</option>
                                {HOURS.map((hour) => (
                                  <option key={hour} value={hour}>{hour}</option>
                                ))}
                              </select>
                            </div>
                          ) : (
                            a.fixed_day && a.fixed_start ? `${a.fixed_day} ${a.fixed_start}` : "—"
                          )}
                        </td>
                        <td>
                          {assignmentEdit === a.id ? (
                            <>
                              <button onClick={async () => {
                                const payload = {
                                  teacher: assignmentEditValues.teacher,
                                  subject: assignmentEditValues.subject,
                                  group: assignmentEditValues.group,
                                  weekly_hours: parseFloat(assignmentEditValues.weekly_hours) || 0,
                                  fixed_day: assignmentEditValues.fixed_day,
                                  fixed_start: assignmentEditValues.fixed_start,
                                  max_session_days: assignmentEditValues.max_session_days,
                                  consecutive_group: assignmentEditValues.consecutive_group,
                                };
                                const res = await updateAssignment(a.id, payload);
                                if (!res.ok) {
                                  alert("No s'ha pogut actualitzar l'assignació docent.");
                                  return;
                                }
                                const newLengths = parseSessionLengths(assignmentEditValues.allowed_session_lengths);
                                const subjectRecord = academicSubjects.find((s) => s.name === assignmentEditValues.subject);
                                if (subjectRecord) {
                                  const subjectRes = await updateSubject(subjectRecord.name, {
                                    name: subjectRecord.name,
                                    weekly_hours: subjectRecord.weekly_hours || 0,
                                    allowed_session_lengths: newLengths,
                                  });
                                  if (!subjectRes.ok) {
                                    alert("S'ha desat l'assignació, però no les durades de sessió de l'assignatura.");
                                  }
                                }
                                setAssignmentEdit(null);
                                await refreshAcademicLists();
                              }}>Desa</button>
                              <button onClick={() => setAssignmentEdit(null)}>Cancel·la</button>
                            </>
                          ) : (
                            <>
                              <button onClick={() => {
                                setAssignmentEdit(a.id);
                                setAssignmentEditValues({
                                  teacher: a.teacher,
                                  subject: a.subject,
                                  group: a.group,
                                  weekly_hours: a.weekly_hours || "",
                                  allowed_session_lengths: formatSessionLengths(a.allowed_session_lengths),
                                  fixed_day: a.fixed_day || "",
                                  fixed_start: a.fixed_start || "",
                                  max_session_days: a.max_session_days || "",
                                  consecutive_group: a.consecutive_group || "",
                                });
                              }}>Edita</button>
                              <button onClick={async () => {
                                const res = await deleteAssignment(a.id);
                                if (res.ok) await refreshAcademicLists(); else alert("No s'ha pogut eliminar l'assignació docent.");
                              }}>Elimina</button>
                              {a.merged_from ? (
                                <button
                                  title="Torna a separar en les dues assignacions originals"
                                  onClick={async () => {
                                    const res = await splitMergedAssignment(a.id);
                                    if (res.ok) await refreshAcademicLists(); else alert(res.data?.detail || "No s'ha pogut separar.");
                                  }}
                                >
                                  Separa
                                </button>
                              ) : null}
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                    <tr>
                      <td></td>
                      <td>
                        <select
                          multiple
                          size={4}
                          value={assignmentDraft.teacher ? assignmentDraft.teacher.split(",").map((t) => t.trim()).filter(Boolean) : []}
                          onChange={(event) => {
                            const selected = Array.from(event.target.selectedOptions).map((option) => option.value);
                            setAssignmentDraft({ ...assignmentDraft, teacher: selected.join(", ") });
                          }}
                        >
                          {teachers.map((t) => (
                            <option key={t.name} value={t.name}>{t.name}</option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select
                          value={assignmentDraft.group}
                          onChange={(event) => setAssignmentDraft({ ...assignmentDraft, group: event.target.value })}
                        >
                          <option value="">Grup</option>
                          {groups.map((g) => (
                            <option key={g.name} value={g.name}>{g.name}</option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select
                          value={assignmentDraft.subject}
                          onChange={(event) => setAssignmentDraft({ ...assignmentDraft, subject: event.target.value })}
                        >
                          <option value="">Assignatura</option>
                          {academicSubjects.map((s) => (
                            <option key={s.name} value={s.name}>{s.name}</option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          type="number"
                          step="0.5"
                          value={assignmentDraft.weekly_hours}
                          placeholder="Setmanals"
                          onChange={(event) => setAssignmentDraft({ ...assignmentDraft, weekly_hours: event.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          min="1"
                          style={{ width: 50 }}
                          value={assignmentDraft.max_session_days}
                          placeholder="Dies"
                          onChange={(event) => setAssignmentDraft({ ...assignmentDraft, max_session_days: event.target.value })}
                        />
                      </td>
                      <td>
                        <div style={{ display: "flex", gap: 4 }}>
                          <select
                            value={assignmentDraft.fixed_day}
                            onChange={(event) => setAssignmentDraft({ ...assignmentDraft, fixed_day: event.target.value })}
                          >
                            <option value="">Sense fixar</option>
                            {DAYS.map((day) => (
                              <option key={day} value={day}>{day}</option>
                            ))}
                          </select>
                          <select
                            value={assignmentDraft.fixed_start}
                            onChange={(event) => setAssignmentDraft({ ...assignmentDraft, fixed_start: event.target.value })}
                            disabled={!assignmentDraft.fixed_day}
                          >
                            <option value="">Hora</option>
                            {HOURS.map((hour) => (
                              <option key={hour} value={hour}>{hour}</option>
                            ))}
                          </select>
                        </div>
                      </td>
                      <td>
                        <input
                          type="text"
                          style={{ width: 90 }}
                          value={assignmentDraft.consecutive_group}
                          placeholder="p.ex. bloc1"
                          onChange={(event) => setAssignmentDraft({ ...assignmentDraft, consecutive_group: event.target.value })}
                        />
                      </td>
                      <td>
                        <button onClick={async () => {
                          if (!assignmentDraft.teacher || !assignmentDraft.subject || !assignmentDraft.group) {
                            alert("Cal indicar professor, assignatura i grup");
                            return;
                          }
                          const res = await createAssignment({
                            teacher: assignmentDraft.teacher,
                            subject: assignmentDraft.subject,
                            group: assignmentDraft.group,
                            weekly_hours: parseFloat(assignmentDraft.weekly_hours) || 0,
                            fixed_day: assignmentDraft.fixed_day,
                            fixed_start: assignmentDraft.fixed_start,
                            max_session_days: assignmentDraft.max_session_days,
                            consecutive_group: assignmentDraft.consecutive_group,
                          });
                          if (res.ok) {
                            setAssignmentDraft({ teacher: "", subject: "", group: "", weekly_hours: "", fixed_day: "", fixed_start: "", max_session_days: "", consecutive_group: "" });
                            await refreshAcademicLists();
                          } else {
                            alert("No s'ha pogut crear l'assignació docent.");
                          }
                        }}>Afegeix</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
                </>
                )}
              </div>
            )}
          </div>
        </section>
      )}
      {isGenerating && <div className="notice">Generant proposta…</div>}

      {currentScreen === "timetable" && (
      <section className="scheduler-layout">
        <div className="timetable-controls">
          <div className="timetable-toolbar">
            <div className="group-tabs" role="tablist" aria-label="Student groups">
              {timetableGroupOptions.map((group) => (
                <button
                  key={group.name}
                  type="button"
                  className={selectedGroup === group.name ? "group-tab group-tab--active" : "group-tab"}
                  onClick={() => setSelectedGroup(group.name)}
                >
                  {group.name}
                </button>
              ))}
            </div>

            <div className="timetable-filter">
              <label>
                Professor
                <select
                  value={teacherFilter}
                  onChange={(event) => setTeacherFilter(event.target.value)}
                  disabled={isFetchingEntities || !selectedGroup}
                >
                  <option value="">Tots</option>
                  {teachers.map((teacher) => (
                    <option key={teacher.name} value={teacher.name}>
                      {teacher.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {proposals && proposals.length > 0 && (
              <div style={{ marginLeft: 12 }}>
                <label>
                  Proposta
                  <select value={selectedProposalId || ""} onChange={(e) => setSelectedProposalId(e.target.value)} style={{ marginLeft: 8 }}>
                    {proposals.map((p) => (
                      <option key={p.id} value={p.id}>{`${p.id} · score ${Math.round(p.score||0)}`}</option>
                    ))}
                  </select>
                </label>
              </div>
            )}
          </div>

          {activities.length > 0 && (
            <div
              className="group-color-legend"
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "10px",
                padding: "8px 4px",
                fontSize: "0.8rem",
              }}
            >
              {Array.from(new Set(activities.map((activity) => activity.group).filter(Boolean)))
                .sort()
                .map((group) => {
                  const color = getGroupColor(group);
                  return (
                    <div key={group} style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                      <span
                        style={{
                          width: "10px",
                          height: "10px",
                          borderRadius: "50%",
                          background: color.background,
                          border: `1px solid ${color.border}`,
                          display: "inline-block",
                        }}
                      />
                      <span>{group}</span>
                    </div>
                  );
                })}
            </div>
          )}

          <div className="timetable" aria-label="Horari">
          <div className="corner-cell" style={{ gridColumn: 1, gridRow: 1 }} />

          {DAYS.map((day, dayIndex) => (
            <div key={day} className="day-header" style={{ gridColumn: dayIndex + 2, gridRow: 1 }}>
              {day}
            </div>
          ))}

          {HOURS.map((hour, hourIndex) => (
            <React.Fragment key={hour}>
              <div className="hour-cell" style={{ gridColumn: 1, gridRow: hourIndex + 2 }}>{hour}</div>

              {DAYS.map((day, dayIndex) => {
                const key = `${day}-${hour}`;
                const isDropTarget = dropTarget === key;

                return (
                  <div
                    key={key}
                    className={isDropTarget ? "slot slot--target" : "slot"}
                    style={{ gridColumn: dayIndex + 2, gridRow: hourIndex + 2 }}
                    onDragOver={(event) => handleDragOver(event, day, hour)}
                    onDragLeave={() => setDropTarget(null)}
                    onDrop={(event) => handleDrop(event, day, hour)}
                  />
                );
              })}
            </React.Fragment>
          ))}

          {Object.entries(visibleActivitiesBySlot).map(([slotKey, slotActivities]) => {
            if (!slotActivities.length) {
              return null;
            }

            const [day, hour] = slotKey.split("-");
            const dayCol = DAYS.indexOf(day);
            const hourRow = HOURS.indexOf(hour);
            if (dayCol === -1 || hourRow === -1) {
              return null;
            }

            const maxDuration = Math.max(
              1,
              ...slotActivities.map((activity) => Number(activity.duration) || 1)
            );
            const rowSpan = Math.min(maxDuration, HOURS.length - hourRow);

            return (
              <div
                key={slotKey}
                className="slot-activities"
                style={{
                  gridColumn: dayCol + 2,
                  gridRow: `${hourRow + 2} / span ${rowSpan}`,
                }}
              >
                {slotActivities.map(renderActivity)}
              </div>
            );
          })}
        </div>
      </div>

        <aside className="side-panel">
          <section>
            <h2>Restriccions de grup</h2>
            {!selectedGroup ? (
              <p className="muted">Seleccioneu un grup per editar les restriccions.</p>
            ) : (
              <div className="restriction-editor">
                <p className="muted">{selectedGroup}</p>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <input
                      type="checkbox"
                      checked={Boolean(groupRestrictionDraft.no_gaps)}
                      onChange={(event) => setGroupRestrictionDraft({ ...groupRestrictionDraft, no_gaps: event.target.checked })}
                    />
                    Sense buits
                  </label>
                  <label>
                    Màx. hores/dia
                    <input
                      type="number"
                      min="0"
                      value={groupRestrictionDraft.max_hours_per_day}
                      onChange={(event) => setGroupRestrictionDraft({ ...groupRestrictionDraft, max_hours_per_day: event.target.value })}
                      style={{ marginLeft: 8 }}
                    />
                  </label>
                  <label>
                    Màx. hores consecutives
                    <input
                      type="number"
                      min="0"
                      value={groupRestrictionDraft.max_consecutive_hours}
                      onChange={(event) => setGroupRestrictionDraft({ ...groupRestrictionDraft, max_consecutive_hours: event.target.value })}
                      style={{ marginLeft: 8 }}
                    />
                  </label>
                </div>

                <div style={{ marginBottom: 12 }}>
                  <h3>Disponibilitat preferida</h3>
                  <div style={{ overflowX: "auto" }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Dia</th>
                          {HOURS.map((hour) => (
                            <th key={hour} style={{ minWidth: 42 }}>{hour}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {DAYS.map((day) => (
                          <tr key={day}>
                            <td>{day}</td>
                            {HOURS.map((hour) => {
                              const slotKey = `${day}-${hour}`;
                              const isPreferred = groupRestrictionDraft.preferred_availability.includes(slotKey);
                              return (
                                <td key={slotKey}>
                                  <button
                                    type="button"
                                    onMouseDown={(event) => { event.preventDefault(); if (!event.shiftKey) setAvailabilitySelectionAnchor(slotKey); }}
                                    onClick={(event) => updateAvailabilitySelection(slotKey, event, groupRestrictionDraft, setGroupRestrictionDraft)}
                                    style={{
                                      width: 16,
                                      height: 16,
                                      padding: 0,
                                      border: `1px solid ${isPreferred ? "#4f46e5" : "#cbd5e1"}`,
                                      background: isPreferred ? "#c7d2fe" : "#fff",
                                    }}
                                  />
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div style={{ marginBottom: 12 }}>
                  <h3>Franges no disponibles</h3>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                    <button type="button" onClick={() => applyUnavailablePreset("no-abans-10", groupRestrictionDraft, setGroupRestrictionDraft)}>No abans de les 10:00</button>
                    <button type="button" onClick={() => applyUnavailablePreset("no-abans-15", groupRestrictionDraft, setGroupRestrictionDraft)}>No abans de les 15:00</button>
                    <button type="button" onClick={() => applyUnavailablePreset("no-despres-17", groupRestrictionDraft, setGroupRestrictionDraft)}>No després de les 17:00</button>
                    <button type="button" onClick={() => applyUnavailablePreset("entre-10-14", groupRestrictionDraft, setGroupRestrictionDraft)}>Entre les 10:00 i les 14:00</button>
                    <button type="button" onClick={() => applyUnavailablePreset("nomes-matins", groupRestrictionDraft, setGroupRestrictionDraft)}>Només matins</button>
                    <button type="button" onClick={() => applyUnavailablePreset("nomes-tardes", groupRestrictionDraft, setGroupRestrictionDraft)}>Només tardes</button>
                    <button type="button" onClick={() => clearAvailabilitySelection(groupRestrictionDraft, setGroupRestrictionDraft, "unavailable_slots", setUnavailableSelectionAnchor)}>Neteja selecció</button>
                  </div>
                  <div className="muted">Clic simple per marcar/desmarcar una franja no disponible manualment (vermell). Maj + clic per seleccionar un rang. Les caselles taronges venen del fitxer FET i no s'editen aquí.</div>
                  <div style={{ overflowX: "auto" }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Dia</th>
                          {HOURS.map((hour) => (
                            <th key={hour} style={{ minWidth: 42 }}>{hour}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {DAYS.map((day) => (
                          <tr key={day}>
                            <td>{day}</td>
                            {HOURS.map((hour) => {
                              const slotKey = `${day}-${hour}`;
                              const isUnavailable = groupRestrictionDraft.unavailable_slots.includes(slotKey);
                              const isFromFet = (groupRestrictionDraft.fet_unavailable_slots || []).includes(`${day} ${hour}`);
                              return (
                                <td key={slotKey}>
                                  <button
                                    type="button"
                                    title={isFromFet ? "No disponible segons el fitxer FET" : undefined}
                                    onMouseDown={(event) => { event.preventDefault(); if (!event.shiftKey) setUnavailableSelectionAnchor(slotKey); }}
                                    onClick={(event) => updateAvailabilitySelection(slotKey, event, groupRestrictionDraft, setGroupRestrictionDraft, "unavailable_slots", unavailableSelectionAnchor, setUnavailableSelectionAnchor)}
                                    style={{
                                      width: 16,
                                      height: 16,
                                      padding: 0,
                                      border: `1px solid ${isUnavailable ? "#b91c1c" : isFromFet ? "#c2680d" : "#cbd5e1"}`,
                                      background: isUnavailable ? "#fecaca" : isFromFet ? "#fed7aa" : "#fff",
                                    }}
                                  />
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                <button type="button" onClick={saveGroupRestrictions} disabled={isSavingGroupRestrictions}>
                  {isSavingGroupRestrictions ? "S'està desant..." : "Desa restriccions"}
                </button>
              </div>
            )}
          </section>

          <section>
            <h2>Dades acadèmiques</h2>

            {!academicSummary ? (
              <p className="muted">Encara no hi ha dades acadèmiques importades.</p>
            ) : (
              <div className="proposal-summary">
                <div className="proposal-metric">
                  <span className="metric-label">Professors</span>
                  <strong>{academicSummary.teachers ?? 0}</strong>
                </div>
                <div className="proposal-metric">
                  <span className="metric-label">Grups</span>
                  <strong>{academicSummary.groups ?? 0}</strong>
                </div>
                <div className="proposal-metric">
                  <span className="metric-label">Assignatures</span>
                  <strong>{academicSummary.subjects ?? 0}</strong>
                </div>
                <div className="proposal-metric">
                  <span className="metric-label">Assignacions docents</span>
                  <strong>{academicSummary.teaching_assignments ?? 0}</strong>
                </div>
                <div className="proposal-metric">
                  <span className="metric-label">Hores de docència setmanals</span>
                  <strong>{academicSummary.weekly_teaching_hours ?? 0}</strong>
                </div>
                <div className="proposal-metric">
                  <span className="metric-label">Restriccions</span>
                  <strong>{academicSummary.restrictions ?? 0}</strong>
                </div>
              </div>
            )}
          </section>

          <section>
            <h2>Proposta generada</h2>

            {!proposal ? (
              <p className="muted">Encara no s'ha generat cap proposta.</p>
            ) : (
              <div className="proposal-summary">
                <div className="proposal-metric">
                  <span className="metric-label">Puntuació</span>
                  <strong>{proposal.score ?? "-"}</strong>
                </div>
                <button
                  type="button"
                  onClick={acceptProposal}
                  disabled={
                    isAccepting
                    || isGenerating
                    || isSaving
                    || (generationStats?.unscheduled_activities_total ?? 0) > 0
                  }
                >
                  {isAccepting ? "Acceptant..." : "Accepta proposta"}
                </button>
                <div className="proposal-metric">
                  <span className="metric-label">Activitats</span>
                  <strong>{proposal.activities?.length ?? 0}</strong>
                </div>
                <div className="proposal-metric">
                  <span className="metric-label">Conflictes</span>
                  <strong>{proposal.conflicts?.length ?? 0}</strong>
                </div>
                <div className="proposal-metric">
                  <span className="metric-label">Fixes reutilitzades</span>
                  <strong>{generationStats?.fixed_activities_total ?? 0}</strong>
                </div>
                <div className="proposal-metric">
                  <span className="metric-label">Activitats per ubicar</span>
                  <strong>{generationStats?.floating_activities_total ?? 0}</strong>
                </div>
                <div className="proposal-metric">
                  <span className="metric-label">Sense franja</span>
                  <strong>{generationStats?.unscheduled_activities_total ?? 0}</strong>
                </div>
                {proposal.warnings?.length ? (
                  <div className="proposal-warning-box">
                    <strong>⚠️ Incidències de generació ({proposal.warnings.length})</strong>
                    <div
                      className="incidents-grid"
                      style={{
                        display: "grid",
                        gap: "12px",
                        gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                        marginTop: "10px",
                      }}
                    >
                      {proposal.warnings.map((warning, index) => {
                        if (typeof warning === "string") {
                          const style = INCIDENT_SEVERITY_STYLES.error;
                          return (
                            <article
                              key={index}
                              className="incident-card"
                              style={{
                                background: style.background,
                                borderLeft: `4px solid ${style.border}`,
                                borderRadius: "8px",
                                padding: "12px 14px",
                              }}
                            >
                              <span style={{ color: style.text }}>{warning}</span>
                            </article>
                          );
                        }

                        // "No s'ha pogut col·locar" és sempre un bloqueig de generació,
                        // per això es classifica com a error. Si en el futur el backend
                        // distingeix bloquejants d'advertències toves, es pot fer servir
                        // classifyConflictSeverity(warning) igual que a les incidències.
                        const style = INCIDENT_SEVERITY_STYLES.error;

                        return (
                          <article
                            key={index}
                            className="incident-card"
                            style={{
                              background: style.background,
                              borderLeft: `4px solid ${style.border}`,
                              borderRadius: "8px",
                              padding: "12px 14px",
                              display: "flex",
                              flexDirection: "column",
                              gap: "6px",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" }}>
                              <strong style={{ color: style.text }}>
                                {warning.subject || "Assignatura desconeguda"}
                              </strong>
                              <span
                                style={{
                                  fontSize: "0.75rem",
                                  fontWeight: 600,
                                  color: style.text,
                                  background: "rgba(255,255,255,0.65)",
                                  borderRadius: "999px",
                                  padding: "2px 10px",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                {style.label}
                              </span>
                            </div>

                            <div
                              style={{
                                fontSize: "0.85rem",
                                color: "#333",
                                display: "grid",
                                gridTemplateColumns: "auto 1fr",
                                gap: "2px 8px",
                              }}
                            >
                              <span className="muted">Professor</span>
                              <span>{warning.teacher || "—"}</span>
                              <span className="muted">Grup</span>
                              <span>{warning.group || "—"}</span>
                              <span className="muted">Durada</span>
                              <span>{warning.duration} blocs</span>
                            </div>

                            {warning.reason && (
                              <span style={{ color: style.text }}>{warning.reason}</span>
                            )}

                            {warning.constraints?.length > 0 && (
                              <div style={{ fontSize: "0.8rem" }}>
                                <span className="muted">Tipus de restricció</span>
                                <ul style={{ margin: "2px 0 0", paddingLeft: "18px" }}>
                                  {warning.constraints.map((c) => (
                                    <li key={c}>{c}</li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            <div>
                              <button
                                type="button"
                                onClick={() => fetchSuggestions(warning.id)}
                                disabled={suggestionsByActivity[warning.id]?.loading}
                                style={{
                                  fontSize: "0.8rem",
                                  padding: "4px 10px",
                                  borderRadius: "6px",
                                  border: `1px solid ${style.border}`,
                                  background: "white",
                                  color: style.text,
                                  cursor: "pointer",
                                }}
                              >
                                {suggestionsByActivity[warning.id]?.loading ? "Cercant..." : "Suggereix franges"}
                              </button>

                              {suggestionsByActivity[warning.id]?.slots.length > 0 && (
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "8px" }}>
                                  {suggestionsByActivity[warning.id].slots.map((slot, slotIndex) => (
                                    <button
                                      key={slotIndex}
                                      type="button"
                                      onClick={() => moveActivity(warning.id, slot.day, slot.start)}
                                      style={{
                                        fontSize: "0.8rem",
                                        padding: "4px 10px",
                                        borderRadius: "6px",
                                        border: "1px solid #ccc",
                                        background: "#f5f5f5",
                                        cursor: "pointer",
                                      }}
                                    >
                                      {slot.day} {slot.start}
                                    </button>
                                  ))}
                                </div>
                              )}

                              {suggestionsByActivity[warning.id] &&
                                !suggestionsByActivity[warning.id].loading &&
                                suggestionsByActivity[warning.id].slots.length === 0 && (
                                  <div style={{ fontSize: "0.8rem", marginTop: "6px", color: style.text }}>
                                    Cap franja disponible.
                                  </div>
                                )}
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </section>

          <section>
            <h2>⚠️ Incidències {conflicts.length > 0 ? `(${conflicts.length})` : ""}</h2>

            {conflicts.length === 0 ? (
              <p className="muted">Cap incidència detectada.</p>
            ) : (
              <div
                className="incidents-grid"
                style={{
                  display: "grid",
                  gap: "12px",
                  gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                }}
              >
                {conflicts.map((conflict, index) => {
                  const severity = classifyConflictSeverity(conflict);
                  const style = INCIDENT_SEVERITY_STYLES[severity];
                  const relatedActivities = resolveConflictActivities(conflict, activities);
                  const subjectLabel = formatConflictField(relatedActivities.map((activity) => activity.subject));
                  const groupLabel = formatConflictField(relatedActivities.map((activity) => activity.group));
                  const roomLabel = formatConflictField(relatedActivities.map((activity) => activity.room));
                  const teacherLabel =
                    conflict.teacher || formatConflictField(relatedActivities.map((activity) => activity.teacher));

                  return (
                    <article
                      key={`${conflict.type}-${index}`}
                      className="incident-card"
                      style={{
                        background: style.background,
                        borderLeft: `4px solid ${style.border}`,
                        borderRadius: "8px",
                        padding: "12px 14px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "6px",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "8px" }}>
                        <strong style={{ color: style.text }}>{conflict.type}</strong>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            color: style.text,
                            background: "rgba(255,255,255,0.65)",
                            borderRadius: "999px",
                            padding: "2px 10px",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {style.label}
                        </span>
                      </div>

                      <span>{conflict.message}</span>

                      <div
                        style={{
                          fontSize: "0.85rem",
                          color: "#333",
                          display: "grid",
                          gridTemplateColumns: "auto 1fr",
                          gap: "2px 8px",
                        }}
                      >
                        {subjectLabel && (
                          <>
                            <span className="muted">Assignatura</span>
                            <span>{subjectLabel}</span>
                          </>
                        )}
                        {teacherLabel && (
                          <>
                            <span className="muted">Professor</span>
                            <span>{teacherLabel}</span>
                          </>
                        )}
                        {groupLabel && (
                          <>
                            <span className="muted">Grup</span>
                            <span>{groupLabel}</span>
                          </>
                        )}
                        {roomLabel && (
                          <>
                            <span className="muted">Aula</span>
                            <span>{roomLabel}</span>
                          </>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          <section>
            <h2>⚠️ Sense franja {displayedUnscheduledActivities.length > 0 ? `(${displayedUnscheduledActivities.length})` : ""}</h2>

            {displayedUnscheduledActivities.length === 0 ? (
              <p className="muted">Cap activitat pendent.</p>
            ) : (
              <div className="unscheduled-list">
                {displayedUnscheduledActivities.map((activity) => (
                  <article
                    key={activity.id}
                    className="unscheduled-card"
                    draggable={Boolean(proposal)}
                    onDragStart={(event) => handleDragStart(event, activity.id)}
                    onDragEnd={() => {
                      setDraggedActivityId(null);
                      setDropTarget(null);
                    }}
                  >
                    <strong>{activity.subject}</strong>
                    <span>{activity.teacher || "Professor pendent"}</span>
                    <small>
                      {activity.group || "Grup sense etiqueta"}
                      {activity.duration ? ` · ${activity.duration} blocs` : ""}
                    </small>
                    {activity.reason ? <p>{activity.reason}</p> : null}
                    {proposal ? <p>Arrossega-la a una franja per provar d'ubicar-la.</p> : null}
                  </article>
                ))}
              </div>
            )}
          </section>

          <section>
            <h2>Explicació activitat</h2>

            {isLoadingExplanation ? (
              <p className="muted">Carregant explicació…</p>
            ) : explanationError ? (
              <p className="muted">{explanationError}</p>
            ) : !selectedExplanation ? (
              <p className="muted">Selecciona "Info" en una activitat per veure el motiu de la seva ubicació.</p>
            ) : (
              <div className="explanation-panel">
                {(() => {
                  const explainedActivity = activities.find(
                    (activity) => activity.id === selectedExplanation.activity_id
                  );
                  if (!explainedActivity) return null;
                  return (
                    <div style={{ marginBottom: 12 }}>
                      <strong style={{ fontSize: "1.05rem" }}>{explainedActivity.subject}</strong>
                      <div className="muted" style={{ fontSize: "0.85rem", marginTop: 4 }}>
                        {explainedActivity.teacher || "Professor pendent"} · {explainedActivity.group || "Grup sense etiqueta"}
                        {explainedActivity.room ? ` · ${explainedActivity.room}` : ""}
                      </div>
                      <div className="muted" style={{ fontSize: "0.85rem" }}>
                        {explainedActivity.day} · {explainedActivity.start}
                      </div>
                    </div>
                  );
                })()}
                <div className="proposal-metric">
                  <span className="metric-label">Contribució local</span>
                  <strong>{selectedExplanation.score_contribution ?? "-"}</strong>
                </div>

                <h3>Restriccions satisfetes</h3>
                {selectedExplanation.satisfied_constraints?.length ? (
                  <ul className="conflict-list">
                    {selectedExplanation.satisfied_constraints.map((item) => (
                      <li key={item}>
                        <strong>{item}</strong>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No hi ha dades.</p>
                )}

                <h3>Preferències vulnerades</h3>
                {selectedExplanation.violated_preferences?.length ? (
                  <ul className="conflict-list">
                    {selectedExplanation.violated_preferences.map((item) => (
                      <li key={item}>
                        <strong>{item}</strong>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Cap preferència vulnerada.</p>
                )}

                <h3>Resum</h3>
                <p className="muted">{selectedExplanation.human_readable_explanation}</p>
              </div>
            )}
          </section>
        </aside>
      </section>
      )}
    </main>
  );
}
