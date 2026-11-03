-- Study Assistant: initial schema, RLS policies and storage bucket.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
create type public.user_role as enum ('student', 'teacher', 'parent');
create type public.timetable_source as enum ('pdf', 'manual');
create type public.document_kind as enum ('textbook', 'material', 'past_paper');
create type public.ingestion_status as enum ('pending', 'processing', 'ready', 'failed');
create type public.exam_difficulty as enum ('easy', 'medium', 'hard');
create type public.exam_status as enum ('generated', 'submitted', 'graded');
create type public.submission_type as enum ('text', 'pdf', 'image');

-- ---------------------------------------------------------------------------
-- Users & relationships
-- ---------------------------------------------------------------------------
create table public.users (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  full_name text,
  role public.user_role not null default 'student',
  created_at timestamptz not null default now()
);

create table public.parent_student_links (
  id uuid primary key default gen_random_uuid(),
  parent_id uuid not null references public.users (id) on delete cascade,
  student_id uuid not null references public.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (parent_id, student_id)
);
create index on public.parent_student_links (student_id);

create table public.notification_preferences (
  parent_id uuid primary key references public.users (id) on delete cascade,
  in_app_enabled boolean not null default true,
  email_enabled boolean not null default true,
  updated_at timestamptz not null default now()
);

-- Mirror new auth users into public.users (role taken from signup metadata).
create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.users (id, email, full_name, role)
  values (
    new.id,
    new.email,
    new.raw_user_meta_data ->> 'full_name',
    coalesce((new.raw_user_meta_data ->> 'role')::public.user_role, 'student')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_auth_user();

-- ---------------------------------------------------------------------------
-- Timetable & tasks
-- ---------------------------------------------------------------------------
create table public.subjects (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.users (id) on delete cascade,
  name text not null,
  color text,
  created_at timestamptz not null default now(),
  unique (student_id, name)
);

create table public.timetables (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.users (id) on delete cascade,
  name text not null default 'My timetable',
  source public.timetable_source not null,
  source_storage_path text,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);
create unique index timetables_one_active_per_student on public.timetables (student_id) where is_active;

create table public.timetable_slots (
  id uuid primary key default gen_random_uuid(),
  timetable_id uuid not null references public.timetables (id) on delete cascade,
  subject_id uuid references public.subjects (id) on delete set null,
  subject_name text not null,
  day_of_week smallint not null check (day_of_week between 0 and 6), -- 0 = Monday
  start_time time not null,
  end_time time not null,
  location text,
  teacher_name text,
  check (end_time > start_time)
);
create index on public.timetable_slots (timetable_id, day_of_week);

create table public.tasks (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.users (id) on delete cascade,
  created_by uuid references public.users (id) on delete set null,
  subject_id uuid references public.subjects (id) on delete set null,
  slot_id uuid references public.timetable_slots (id) on delete set null,
  title text not null,
  description text,
  due_date date not null default current_date,
  completed boolean not null default false,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on public.tasks (student_id, due_date);

-- ---------------------------------------------------------------------------
-- Documents
-- ---------------------------------------------------------------------------
create table public.documents (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.users (id) on delete cascade,
  subject_id uuid references public.subjects (id) on delete set null,
  title text not null,
  filename text not null,
  kind public.document_kind not null,
  namespace text not null check (namespace in ('materials', 'pastpapers')),
  storage_path text not null unique,
  mime_type text not null default 'application/pdf',
  size_bytes bigint,
  is_shared boolean not null default false,
  page_count integer,
  chunk_count integer,
  status public.ingestion_status not null default 'pending',
  error text,
  created_at timestamptz not null default now(),
  check ((kind = 'past_paper') = (namespace = 'pastpapers'))
);
create index on public.documents (owner_id);

-- ---------------------------------------------------------------------------
-- Exams
-- ---------------------------------------------------------------------------
create table public.exams (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.users (id) on delete cascade,
  topic text not null,
  total_marks integer not null check (total_marks > 0),
  difficulty public.exam_difficulty not null,
  status public.exam_status not null default 'generated',
  instructions text,
  created_at timestamptz not null default now()
);
create index on public.exams (student_id, created_at desc);

create table public.exam_questions (
  id uuid primary key default gen_random_uuid(),
  exam_id uuid not null references public.exams (id) on delete cascade,
  position integer not null,
  question_text text not null,
  marks integer not null check (marks > 0),
  mark_scheme text not null,
  topic text,
  source_doc_id uuid references public.documents (id) on delete set null,
  source_page integer,
  source_storage_path text,
  unique (exam_id, position)
);

create table public.exam_submissions (
  id uuid primary key default gen_random_uuid(),
  exam_id uuid not null references public.exams (id) on delete cascade,
  student_id uuid not null references public.users (id) on delete cascade,
  submission_type public.submission_type not null,
  answer_text text,
  storage_path text,
  total_awarded numeric(6, 2),
  total_available integer,
  focus_report jsonb,
  submitted_at timestamptz not null default now(),
  graded_at timestamptz
);
create index on public.exam_submissions (exam_id);

create table public.grades (
  id uuid primary key default gen_random_uuid(),
  submission_id uuid not null references public.exam_submissions (id) on delete cascade,
  exam_id uuid not null references public.exams (id) on delete cascade,
  question_id uuid not null references public.exam_questions (id) on delete cascade,
  awarded_marks numeric(6, 2) not null check (awarded_marks >= 0),
  max_marks integer not null,
  feedback text,
  topic text,
  created_at timestamptz not null default now(),
  unique (submission_id, question_id)
);

-- ---------------------------------------------------------------------------
-- Reports & in-app notifications
-- ---------------------------------------------------------------------------
create table public.daily_reports (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.users (id) on delete cascade,
  report_date date not null,
  total_tasks integer not null default 0,
  completed_tasks integer not null default 0,
  completion_rate numeric(5, 2) not null default 0,
  summary text,
  details jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (student_id, report_date)
);

create table public.notifications (
  id uuid primary key default gen_random_uuid(),
  recipient_id uuid not null references public.users (id) on delete cascade,
  student_id uuid references public.users (id) on delete cascade,
  kind text not null,
  title text not null,
  body text,
  data jsonb not null default '{}'::jsonb,
  read_at timestamptz,
  created_at timestamptz not null default now()
);
create index on public.notifications (recipient_id, created_at desc);

-- ---------------------------------------------------------------------------
-- RLS helpers
-- ---------------------------------------------------------------------------
create or replace function public.current_user_role()
returns public.user_role
language sql stable security definer set search_path = public
as $$ select role from public.users where id = auth.uid() $$;

create or replace function public.is_linked_parent(p_student_id uuid)
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1 from public.parent_student_links
    where parent_id = auth.uid() and student_id = p_student_id
  )
$$;

create or replace function public.is_teacher()
returns boolean
language sql stable security definer set search_path = public
as $$ select coalesce(public.current_user_role() = 'teacher', false) $$;

-- "Can read this student's rows": the student, a linked parent, or a teacher.
create or replace function public.can_read_student(p_student_id uuid)
returns boolean
language sql stable security definer set search_path = public
as $$ select p_student_id = auth.uid() or public.is_linked_parent(p_student_id) or public.is_teacher() $$;

-- ---------------------------------------------------------------------------
-- RLS policies
-- ---------------------------------------------------------------------------
alter table public.users enable row level security;
alter table public.parent_student_links enable row level security;
alter table public.notification_preferences enable row level security;
alter table public.subjects enable row level security;
alter table public.timetables enable row level security;
alter table public.timetable_slots enable row level security;
alter table public.tasks enable row level security;
alter table public.documents enable row level security;
alter table public.exams enable row level security;
alter table public.exam_questions enable row level security;
alter table public.exam_submissions enable row level security;
alter table public.grades enable row level security;
alter table public.daily_reports enable row level security;
alter table public.notifications enable row level security;

-- users
create policy users_select on public.users for select
  using (id = auth.uid() or public.is_linked_parent(id) or (public.is_teacher() and role = 'student'));
create policy users_update_self on public.users for update
  using (id = auth.uid())
  with check (id = auth.uid() and role = public.current_user_role());

-- parent_student_links
create policy links_select on public.parent_student_links for select
  using (parent_id = auth.uid() or student_id = auth.uid() or public.is_teacher());
create policy links_student_insert on public.parent_student_links for insert
  with check (student_id = auth.uid() or public.is_teacher());
create policy links_delete on public.parent_student_links for delete
  using (student_id = auth.uid() or parent_id = auth.uid() or public.is_teacher());

-- notification_preferences (parent owns their row)
create policy prefs_owner on public.notification_preferences for all
  using (parent_id = auth.uid()) with check (parent_id = auth.uid());

-- subjects / timetables: student owns; linked parents + teachers read
create policy subjects_read on public.subjects for select using (public.can_read_student(student_id));
create policy subjects_write on public.subjects for all
  using (student_id = auth.uid()) with check (student_id = auth.uid());

create policy timetables_read on public.timetables for select using (public.can_read_student(student_id));
create policy timetables_write on public.timetables for all
  using (student_id = auth.uid()) with check (student_id = auth.uid());

create policy slots_read on public.timetable_slots for select using (
  exists (select 1 from public.timetables t where t.id = timetable_id and public.can_read_student(t.student_id))
);
create policy slots_write on public.timetable_slots for all using (
  exists (select 1 from public.timetables t where t.id = timetable_id and t.student_id = auth.uid())
) with check (
  exists (select 1 from public.timetables t where t.id = timetable_id and t.student_id = auth.uid())
);

-- tasks: student owns; teachers can create/update; parents read linked children
create policy tasks_read on public.tasks for select using (public.can_read_student(student_id));
create policy tasks_insert on public.tasks for insert
  with check ((student_id = auth.uid() or public.is_teacher()) and created_by = auth.uid());
create policy tasks_update on public.tasks for update
  using (student_id = auth.uid() or public.is_teacher())
  with check (student_id = auth.uid() or public.is_teacher());
create policy tasks_delete on public.tasks for delete
  using (student_id = auth.uid() or created_by = auth.uid());

-- documents: owner manages; shared docs readable by everyone signed in;
-- linked parents can read their child's documents
create policy documents_read on public.documents for select
  using (owner_id = auth.uid() or is_shared or public.is_linked_parent(owner_id));
create policy documents_write on public.documents for all
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

-- exams & children tables
create policy exams_read on public.exams for select using (public.can_read_student(student_id));
create policy exams_write on public.exams for all
  using (student_id = auth.uid()) with check (student_id = auth.uid());

create policy exam_questions_read on public.exam_questions for select using (
  exists (select 1 from public.exams e where e.id = exam_id and public.can_read_student(e.student_id))
);

create policy submissions_read on public.exam_submissions for select using (public.can_read_student(student_id));
create policy submissions_insert on public.exam_submissions for insert with check (student_id = auth.uid());

create policy grades_read on public.grades for select using (
  exists (select 1 from public.exams e where e.id = exam_id and public.can_read_student(e.student_id))
);

-- daily reports: written by the backend (service role); readable per student access rules
create policy daily_reports_read on public.daily_reports for select using (public.can_read_student(student_id));

-- notifications: recipient only
create policy notifications_read on public.notifications for select using (recipient_id = auth.uid());
create policy notifications_update on public.notifications for update
  using (recipient_id = auth.uid()) with check (recipient_id = auth.uid());

-- ---------------------------------------------------------------------------
-- Storage bucket (private). Objects live under "<owner_id>/...".
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;

create policy "documents_owner_read" on storage.objects for select
  using (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "documents_owner_write" on storage.objects for insert
  with check (bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text);
