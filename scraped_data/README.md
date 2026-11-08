# Scraped data (2026-11-08)

Raw material for the next round of changes. Nothing here is used by the app yet; it gets turned into seed files under `app/data/`.

| File | Source | What it holds |
|---|---|---|
| `is_faculty_profiles.json` | https://nitte.edu.in/nmamit/department-information-science.php (the "Read More" popups) | 36 IS faculty: name, designation, email, joining date, photo URL, and profile sections (Educational Qualifications, Areas of Interest, Subjects Teaching, Past Experience, Publications, Responsibilities, Projects Guided, Memberships, Achievements) |
| `teacher_cabins_cabincompass.json` | https://find-my-teacher.vercel.app (its public API `find-my-teacher.onrender.com/api/search`) | 115 teachers across all departments: name, branch, floor/block, walking directions (photos left out). 15 are IS |
| `see_timetable_7sem_dec2026.md` | `TEMP/4) SEE Time Table - 7 Sem BTech - Dec 2026.pdf` | 7th sem B.Tech SEE theory timetable, 10-22 Dec 2026, 1:00-4:00 PM, all branches (TENTATIVE) |
| `ems_events.json` | https://ems.nmamit.in/events (its public API `/api/public/upcoming-bookings`) | 75 approved campus bookings, 2026-11-08 to 2027-01-23: title, description, venue, date, times, type, department. Organiser phone numbers and emails left out |
| `ems/` | ems.nmamit.in | Text, screenshots and links of the public Events and Login pages (what EMS offers) |
| `nmamit_is_dept_text.txt` | IS department page | All visible text of the page (vision, labs, testimonials, faculty) |
| `raw/` | all of the above | Original HTML and JS as downloaded |

Refresh: the scripts that made these are simple GETs against the public endpoints above; no login was used.
