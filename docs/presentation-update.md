# Shoqan Day: verified product update for the presentation

Prepared 2 October 2026 from the implemented local MVP and its verification results. This is slide-ready copy and an edit brief; the Library PowerPoint itself could not be materialized in this run and has not been replaced.

## Product state to present

Shoqan Day turns an assignment into a study plan around the student's fixed classes. The student can paste the assignment text; configured Gemini can suggest the subject, requirements, deadline, and study stages. The student reviews and edits the draft before confirming it. The block table lets them change proposed dates, start times, and durations; validation rejects uncovered dates, class/transition conflicts, overlapping blocks, excess daily minutes, and blocks past the deadline. Remaining minutes stay visible as unplaced. Manual task entry remains available without an AI key. The planner looks ahead at least 14 days and extends to the task deadline up to a 30-day cap.

If a schedule or group change conflicts with saved blocks, the app surfaces the conflict. It first shows a proposed replan; applying it requires a separate confirmation. Completed blocks remain in place. A changed profile is checked against its restored schedule.

The group selector has capacity for up to 10 imported group profiles across CSV imports, plus two profiles from the clearly labeled synthetic demo CSV. One uploaded CSV can contain multiple groups. Each imported group has its own schedule source, coverage, tasks, and saved blocks. Reimporting a matching group replaces only its schedule and preserves the plan so conflicts can be reviewed. There is no official timetable sync and no fabricated group schedule.

## Data disclosure

- The built-in `data/schedule_demo.csv` is a synthetic demonstration schedule.
- The dated sample `data/isr242_2026-09-28.csv` contains a manually transcribed, user-supplied archive snapshot for group ИСР-242уск, covering 28 September–3 October 2026. Its coverage expired on 3 October 2026. It is not an official university feed and is not kept in sync.
- The planner must treat dates outside a schedule's declared coverage as unknown, rather than as free time. This sample's six-day coverage limits the planner even though its lookahead can reach 30 days.
- The MVP has no official university integration, cross-device account sync, or push notifications. Browser storage and user-managed JSON export/import are local persistence and backup paths.
- Gemini analysis needs the configured server-side API key. Without it, manual entry works; live Gemini behavior was not exercised in this verification run.

## Verification evidence

- 67 Python tests passed, including Streamlit AppTests for same-run completion updates, schedule-conflict warnings, confirmation before replanning, restored profiles, and isolated group switching.
- Unit coverage verifies imports of 10 groups, atomic rejection above the limit, per-group source/coverage preservation, plan retention on schedule replacement, editable auto-plans, deadline lookahead, and honest unplaced minutes.
- The JavaScript storage suite passed. `compileall`, `pip check`, and `git diff --check` passed.
- The local Streamlit health endpoint returned HTTP 200. A current browser screenshot could not be captured in this Windows session; the older presentation screenshot should be labeled as a 30 September 2026 snapshot and not presented as the current UI.
- No official-data validation, live Gemini API test, or end-to-end browser visual test is claimed.

## Suggested edits to the existing deck

- Replace the old test count and public commit reference with the verification evidence above. State that this is a local, unpublished MVP review if referring to this working tree.
- Update the workflow/demo slide to show assignment draft → student review → editable plan preview → confirmation → preparation blocks around fixed classes → completion tracking.
- Add the conflict preview and explicit apply step; note that completed blocks are preserved.
- Keep the source and coverage caveat beside any schedule example. Label the demo CSV synthetic and the ИСР-242уск dates as a manually transcribed, user-supplied snapshot. State that users may import up to 10 groups.
- Keep the existing 30 September screenshot only as an archival screenshot until a fresh supported-browser capture is available.

The source PowerPoint `Shoqan_Day_IDEATHON_2026.pptx` remains at Library version 3. Its paired PDF export has not been updated.
