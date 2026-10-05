import unittest

from schedule_proposal import (
    export_proposal_csv, generate_proposal, parse_proposal_input, verify_proposal,
)


def inputs(requests, rooms, unavailable="resource_type,resource,day,start_time,end_time\n"):
    return parse_proposal_input(requests, rooms, unavailable)


class ScheduleProposalTests(unittest.TestCase):
    def test_complete_proposal_for_ten_groups_is_stable_and_verified(self):
        request_lines = ["group,subject,teacher,room_type,students,sessions_per_week"]
        for i in range(10):
            request_lines.append(f"GROUP-{i:02},Course {i},Shared lecturer,lecture,20,2")
        room_lines = ["room,room_type,capacity,building"]
        for i in range(4):
            room_lines.append(f"R{i:02},lecture,30,Campus {i % 2}")
        problem = inputs("\n".join(request_lines), "\n".join(room_lines))

        first = generate_proposal(problem)
        second = generate_proposal(problem)

        self.assertEqual(first, second)
        self.assertEqual(first["status"], "complete")
        self.assertEqual(len(first["meetings"]), 20)
        self.assertTrue(verify_proposal(problem, first["meetings"])["valid"])
        self.assertEqual({item["group"] for item in first["meetings"]},
                         {f"GROUP-{i:02}" for i in range(10)})

    def test_resource_availability_and_ten_minute_buffer_are_respected(self):
        for resource_type, resource in [("group", "G"), ("teacher", "T"), ("room", "A")]:
            with self.subTest(resource_type=resource_type):
                problem = inputs(
                    "group,subject,teacher,room_type,students,sessions_per_week\nG,Course,T,lecture,20,1",
                    "room,room_type,capacity,building\nA,lecture,30,North",
                    f"resource_type,resource,day,start_time,end_time\n{resource_type},{resource},Monday,09:00,10:00\n",
                )
                proposal = generate_proposal(problem)
                self.assertEqual(proposal["status"], "complete")
                self.assertNotEqual((proposal["meetings"][0]["day"], proposal["meetings"][0]["start_time"]),
                                    ("Monday", "09:00"))
                self.assertTrue(verify_proposal(problem, proposal["meetings"])["valid"])

    def test_partial_draft_names_room_capacity_reason_and_exports_status(self):
        problem = inputs(
            "group,subject,teacher,room_type,students,sessions_per_week\nG,Lab,T,lab,40,1",
            "room,room_type,capacity,building\nA,lecture,20,North",
        )
        proposal = generate_proposal(problem)
        self.assertEqual(proposal["status"], "partial")
        self.assertEqual(proposal["meetings"], [])
        self.assertIn("вместимости", proposal["unplaced"][0]["reason"])
        self.assertTrue(verify_proposal(problem, proposal["meetings"])["valid"])
        exported = export_proposal_csv(problem, proposal).decode("utf-8-sig")
        self.assertIn("not_placed", exported)
        self.assertIn(",Lab,", exported)

    def test_bounded_search_can_still_return_a_valid_complete_greedy_draft(self):
        problem = inputs(
            "group,subject,teacher,room_type,students,sessions_per_week\nG,Course,T,lecture,10,2",
            "room,room_type,capacity,building\nA,lecture,20,North",
        )
        proposal = generate_proposal(problem, node_budget=1)
        self.assertTrue(proposal["search_limited"])
        self.assertEqual(proposal["status"], "complete")
        self.assertTrue(proposal["verification"]["complete"])
        self.assertTrue(proposal["verification"]["valid"])

    def test_independent_checker_catches_teacher_double_booking(self):
        cases = [
            ("преподаватель", "G1,Course 1,T,lecture,20,1\nG2,Course 2,T,lecture,20,1", "A,lecture,30,North\nB,lecture,30,South"),
            ("группа", "G,Course 1,T1,lecture,20,1\nG,Course 2,T2,lecture,20,1", "A,lecture,30,North\nB,lecture,30,South"),
            ("аудитория", "G1,Course 1,T1,lecture,20,1\nG2,Course 2,T2,lecture,20,1", "A,lecture,30,North"),
        ]
        for resource, request_rows, room_rows in cases:
            with self.subTest(resource=resource):
                problem = inputs("group,subject,teacher,room_type,students,sessions_per_week\n" + request_rows,
                                 "room,room_type,capacity,building\n" + room_rows)
                proposal = generate_proposal(problem)
                self.assertEqual(proposal["status"], "complete")
                changed = [dict(item) for item in proposal["meetings"]]
                changed[1]["day"] = changed[0]["day"]
                changed[1]["start_time"] = changed[0]["start_time"]
                changed[1]["end_time"] = changed[0]["end_time"]
                check = verify_proposal(problem, changed)
                self.assertFalse(check["valid"])
                self.assertTrue(any(resource in issue for issue in check["issues"]))

    def test_input_rejects_more_than_ten_groups_and_invalid_resource_reference(self):
        rows = ["group,subject,teacher,room_type,students,sessions_per_week"]
        for i in range(11):
            rows.append(f"G{i},Course {i},T{i},lecture,10,1")
        room_csv = "room,room_type,capacity,building\nA,lecture,30,North"
        with self.assertRaisesRegex(ValueError, "10 разных групп"):
            inputs("\n".join(rows), room_csv)
        with self.assertRaisesRegex(ValueError, "не найден"):
            inputs(
                "group,subject,teacher,room_type,students,sessions_per_week\nG,C,T,lecture,10,1",
                room_csv,
                "resource_type,resource,day,start_time,end_time\nroom,Missing,Monday,09:00,10:00",
            )

    def test_mvp_limits_reject_inputs_before_large_domain_build(self):
        room_csv = "room,room_type,capacity,building\nA,lecture,30,North"
        requests = ["group,subject,teacher,room_type,students,sessions_per_week"]
        for i in range(7):
            requests.append(f"G{i},Course {i},T{i},any,20,5")
        with self.assertRaisesRegex(ValueError, "30 занятий"):
            inputs("\n".join(requests), room_csv)

        requests_csv = "group,subject,teacher,room_type,students,sessions_per_week\nG,C,T,any,20,1"
        room_rows = ["room,room_type,capacity,building"]
        room_rows.extend(f"R{i},lecture,30,North" for i in range(13))
        with self.assertRaisesRegex(ValueError, "12 строк"):
            inputs(requests_csv, "\n".join(room_rows))

        busy = ["resource_type,resource,day,start_time,end_time"]
        busy.extend("group,G,Monday,00:00,00:01" for _ in range(101))
        with self.assertRaisesRegex(ValueError, "100 строк"):
            inputs(requests_csv, room_csv, "\n".join(busy))

    def test_formula_leading_subject_is_safe_in_review_csv(self):
        problem = inputs(
            "group,subject,teacher,room_type,students,sessions_per_week\nG,=SUM(1+1),T,lecture,10,1",
            "room,room_type,capacity,building\nA,lecture,20,North",
        )
        proposal = generate_proposal(problem)
        exported = export_proposal_csv(problem, proposal).decode("utf-8-sig")
        self.assertIn("'=SUM(1+1)", exported)


if __name__ == "__main__":
    unittest.main()
