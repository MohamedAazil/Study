import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { UserProfile } from "../lib/types";

/** Teachers/parents pick which student they are viewing. */
export default function StudentPicker({ value, onChange }: { value?: string; onChange: (id: string) => void }) {
  const [students, setStudents] = useState<UserProfile[]>([]);
  useEffect(() => {
    api.auth.students().then((list) => {
      setStudents(list);
      if (!value && list[0]) onChange(list[0].id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (!students.length) return <span className="muted">No students available.</span>;
  return (
    <label className="inline">
      Student
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        {students.map((s) => (
          <option key={s.id} value={s.id}>
            {s.full_name || s.email}
          </option>
        ))}
      </select>
    </label>
  );
}
