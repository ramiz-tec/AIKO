import math
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QLabel,
    QMainWindow,
    QStackedWidget,
)
from PyQt5.QtCore import QThreadPool
from PyQt5.QtTest import QTest

from backend import Workspace
from frontend.GUI import (
    BreakingNewsPanel,
    ConversationMapScreen,
    HologramCanvas,
    OrbMapCanvas,
    ReminderNotification,
    SetSpeechLevel,
    WorkspaceScreen,
)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.temporary_directory.name) / "Workspace"
        self.root_patch = patch.object(Workspace, "WORKSPACE_ROOT", self.workspace_root)
        self.root_patch.start()
        self.generator_patch = patch.object(
            Workspace,
            "generate_design_parts",
            return_value=[{
                "name": "Generated Part",
                "shape": "box",
                "position": [0.0, 0.0, 0.0],
                "size": [1.0, 1.0, 1.0],
            }],
        )
        self.generator_patch.start()
        Workspace.ensure_workspace()
        self.addCleanup(self.generator_patch.stop)
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.temporary_directory.cleanup)

    def test_imports_models_and_moves_them_into_workspace_folders(self):
        source = Path(self.temporary_directory.name) / "sample.obj"
        source.write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
            encoding="utf-8",
        )
        folder = Workspace.create_folder("Design files")

        imported = Workspace.import_project(source, "3D")
        moved = Workspace.move_project(imported, folder)
        items = Workspace.list_projects("3D", folder)

        self.assertEqual(moved.parent, folder)
        self.assertEqual(items[0]["name"], "sample")
        self.assertEqual(items[0]["kind"], "model")
        self.assertEqual(Workspace.get_active_project(), moved.resolve())

    def test_workspace_rejects_files_outside_the_selected_folder(self):
        other_folder = Path(self.temporary_directory.name) / "outside"
        other_folder.mkdir()

        with self.assertRaisesRegex(ValueError, "inside the selected workspace"):
            Workspace.list_projects("3D", other_folder)

    def test_tinkercad_link_is_kept_as_a_manual_open_link(self):
        link = Workspace.add_external_project(
            "Attachment",
            "https://www.tinkercad.com/things/6j77N2wkiZT-attachment",
        )

        self.assertEqual(link.parent, (self.workspace_root / "3D").resolve())
        self.assertEqual(
            Workspace.list_projects("3D")[0]["kind"],
            "link",
        )

    def test_parametric_design_can_add_remove_parts_and_export_stl(self):
        generated_cylinder = [{
            "name": "Cylinder",
            "shape": "cylinder",
            "position": [0.0, 0.0, 0.0],
            "size": [1.0, 1.0, 1.0],
        }]
        with patch.object(
            Workspace, "generate_design_parts", return_value=generated_cylinder
        ):
            project = Workspace.create_design("A cylinder test")
        added = Workspace.add_part(project, "sphere")
        exported = Path(self.temporary_directory.name) / "design.stl"
        Workspace.export_design_to_stl(project, exported)

        triangles = Workspace.load_mesh(exported)
        removed = Workspace.remove_part(project, 1)

        self.assertEqual(added["shape"], "sphere")
        self.assertEqual(removed["shape"], "sphere")
        self.assertEqual(len(Workspace.load_mesh(project)), 64)
        self.assertEqual(len(triangles), 64 + 8 * 16 * 2)

    def test_building_prompt_uses_ai_generated_geometry(self):
        generated_parts = [
            {"name": "Foundation", "shape": "box", "position": [0, 0, 0],
             "size": [2, 2, 0.3]},
            {"name": "Main Tower", "shape": "box", "position": [0, 0, 2],
             "size": [1, 1, 4]},
            {"name": "Roof", "shape": "cylinder", "position": [0, 0, 4.2],
             "size": [0.8, 0.8, 0.4]},
        ]
        with patch.object(
            Workspace, "generate_design_parts", return_value=generated_parts
        ) as generate:
            project = Workspace.create_design("an art deco building")
        design = Workspace.load_design(project)
        shapes = {part["shape"] for part in design["parts"]}
        triangles = Workspace.load_mesh(project)

        generate.assert_called_once_with("an art deco building")
        self.assertEqual(len(design["parts"]), 3)
        self.assertIn("Main Tower", {part["name"] for part in design["parts"]})
        self.assertIn("cylinder", shapes)
        self.assertGreaterEqual(len(triangles), 88)

    def test_city_prompt_uses_ai_generated_scene_parts(self):
        generated_parts = [
            {"name": "Street", "shape": "box", "position": [0, 0, 0],
             "size": [8, 1, 0.1]},
            {"name": "Office Tower", "shape": "box", "position": [-2, 0, 2],
             "size": [1, 1, 4]},
            {"name": "Clock Tower", "shape": "cylinder", "position": [2, 0, 2],
             "size": [1, 1, 4]},
        ]
        with patch.object(
            Workspace, "generate_design_parts", return_value=generated_parts
        ) as generate:
            project = Workspace.create_design("a coastal city at night")
        design = Workspace.load_design(project)
        triangles = Workspace.load_mesh(project)

        generate.assert_called_once_with("a coastal city at night")
        self.assertEqual(len(design["parts"]), 3)
        self.assertEqual(len(triangles), 88)

    def test_part_operations_require_editable_projects_and_keep_one_part(self):
        project = Workspace.create_design("A box")
        with self.assertRaisesRegex(ValueError, "at least one part"):
            Workspace.remove_part(project, 0)
        with self.assertRaisesRegex(ValueError, "box, sphere, or cylinder"):
            Workspace.add_part(project, "torus")

    def test_workbench_transform_state_round_trips_for_workspace_models(self):
        project = Workspace.create_design("A saved workbench model")
        transform = {
            "offset": [0.25, -0.5, 0.75],
            "scale": 1.4,
            "rotation": [0.1, 0.2, 0.3],
            "reference_size": 2.0,
            "fit_scale": 0.5,
        }

        Workspace.save_workbench_transform(project, transform)

        self.assertEqual(Workspace.load_workbench_transform(project), transform)

    def test_obj_parser_triangulates_polygon_faces(self):
        source = Path(self.temporary_directory.name) / "quad.obj"
        source.write_text(
            "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nf 1 2 3 4\n",
            encoding="utf-8",
        )

        self.assertEqual(len(Workspace.load_mesh(source)), 2)

    def test_workbench_loader_preserves_object_scale_for_assembly_views(self):
        source = Path(self.temporary_directory.name) / "scaled.obj"
        source.write_text(
            "v 0 0 0\nv 10 0 0\nv 0 5 0\nf 1 2 3\n",
            encoding="utf-8",
        )

        normalized = Workspace.load_mesh(source)
        workbench, materials = Workspace.load_mesh_for_workbench(source)

        normalized_width = max(vertex[0] for vertex in normalized[0]) - min(
            vertex[0] for vertex in normalized[0]
        )
        workbench_width = max(vertex[0] for vertex in workbench[0]) - min(
            vertex[0] for vertex in workbench[0]
        )
        self.assertAlmostEqual(workbench_width / normalized_width, 10)
        self.assertIsNone(materials)

    def test_invalid_obj_indices_are_reported(self):
        source = Path(self.temporary_directory.name) / "invalid.obj"
        source.write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 0 2 3\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "Invalid OBJ face"):
            Workspace.load_mesh(source)

    def test_tinkercad_eagle_board_renders_outline_component_and_nets(self):
        source = Path(self.temporary_directory.name) / "sample.brd"
        source.write_text(
            """<?xml version="1.0"?>
<!DOCTYPE eagle SYSTEM "eagle.dtd">
<eagle version="9.7.0"><drawing><board>
  <plain>
    <wire x1="0" y1="0" x2="10" y2="0" layer="20"/>
    <wire x1="10" y1="0" x2="10" y2="10" layer="20"/>
    <wire x1="10" y1="10" x2="0" y2="10" layer="20"/>
    <wire x1="0" y1="10" x2="0" y2="0" layer="20"/>
  </plain>
  <libraries><library name="Tinkercad"><packages>
    <package name="RESISTOR">
      <wire x1="-2" y1="-1" x2="2" y2="-1" layer="21"/>
      <wire x1="2" y1="-1" x2="2" y2="1" layer="21"/>
      <wire x1="2" y1="1" x2="-2" y2="1" layer="21"/>
      <wire x1="-2" y1="1" x2="-2" y2="-1" layer="21"/>
      <pad name="1" x="-1" y="0" diameter="1"/>
      <pad name="2" x="1" y="0" diameter="1"/>
    </package>
  </packages></library></libraries>
  <elements>
    <element name="R1" value="10k" package="RESISTOR" x="5" y="5" rot="R90"/>
  </elements>
  <signals><signal name="VCC">
    <wire x1="2" y1="2" x2="8" y2="8" width="0" layer="19"/>
  </signal></signals>
</board></drawing></eagle>
""",
            encoding="utf-8",
        )

        mesh, materials = Workspace.load_mesh_with_materials(source)

        self.assertGreater(len(mesh), 80)
        self.assertEqual(len(materials), len(mesh))
        self.assertIn("board", materials)
        self.assertIn("pads", materials)
        self.assertIn("unrouted", materials)
        coordinates = [
            coordinate
            for triangle in mesh
            for vertex in triangle
            for coordinate in vertex
        ]
        self.assertTrue(all(-0.5 <= coordinate <= 0.5 for coordinate in coordinates))
        self.assertLess(min(vertex[2] for triangle in mesh for vertex in triangle), 0)
        self.assertGreater(max(vertex[2] for triangle in mesh for vertex in triangle), 0)

    def test_invalid_eagle_board_xml_is_reported(self):
        source = Path(self.temporary_directory.name) / "invalid.brd"
        source.write_text("<eagle>", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Could not parse EAGLE board XML"):
            Workspace.load_mesh(source)

    def test_removed_workspace_file_is_recoverable_from_trash(self):
        source = Path(self.temporary_directory.name) / "sample.obj"
        source.write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
            encoding="utf-8",
        )
        imported = Workspace.import_project(source)

        target = Workspace.remove_project(Workspace.find_project("sample.obj"))

        self.assertFalse(imported.exists())
        self.assertTrue(target.is_file())
        self.assertEqual(target.parent.name, ".Trash")

    def test_workspace_command_parser_requires_explicit_actions(self):
        self.assertEqual(
            Workspace.parse_workspace_command("create a 3D design of a box"),
            ("create", "a box"),
        )
        self.assertEqual(
            Workspace.parse_workspace_command("add a cylinder to the current project"),
            ("add_part", "cylinder"),
        )
        self.assertEqual(
            Workspace.parse_workspace_command("remove workspace file sample.obj"),
            ("remove_file", "sample.obj"),
        )
        self.assertIsNone(Workspace.parse_workspace_command("maybe remove the file"))

    def test_workspace_voice_commands_cover_projects_folders_and_workbench_buttons(self):
        requests = {
            "open workspace": ("open", ""),
            "close workspace": ("close_workspace", ""),
            "create folder named Prototype Parts": (
                "create_folder",
                "Prototype Parts",
            ),
            "create folder": ("create_folder", ""),
            "switch to circuits": ("switch_type", "Circuits"),
            "open project bridge.aiko3d": ("open_project", "bridge.aiko3d"),
            "open folder Prototype Parts": (
                "open_project",
                "Prototype Parts",
            ),
            "close current project": ("close_project", ""),
            "shrink selected hologram": ("shrink", ""),
            "shrink": ("shrink", ""),
            "enlarge item": ("enlarge", ""),
            "rotate selected item around x axis by 30 degrees": (
                "rotate",
                "x 30",
            ),
            "rotate along z axis": ("rotate", "z 15"),
            "snap the holograms": ("combine", ""),
            "clear the workbench": ("clear_workbench", ""),
            "exit focus": ("exit_focus", ""),
            "remove last hologram": ("remove_last_hologram", ""),
            "rotate selected": ("toggle_rotation", ""),
            "add part": ("add_part", ""),
            "remove file": ("remove_file", ""),
            "import file C:\\models\\bridge.obj": (
                "import_file",
                "C:\\models\\bridge.obj",
            ),
            "export as STL": ("export_stl", ""),
            "move part Base along y to 3.5": (
                "move_part",
                "Base|y|3.5",
            ),
            "move part": ("move_part", ""),
            "add Tinkercad link Desk Lamp at "
            "https://www.tinkercad.com/things/abc-123": (
                "add_link",
                "Desk Lamp|https://www.tinkercad.com/things/abc-123",
            ),
            "remove file Bridge": ("remove_file", "Bridge"),
        }
        for request, expected in requests.items():
            with self.subTest(request=request):
                self.assertEqual(
                    Workspace.parse_workspace_command(request),
                    expected,
                )


class WorkspaceInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.temporary_directory.name) / "Workspace"
        self.root_patch = patch.object(
            Workspace, "WORKSPACE_ROOT", self.workspace_root
        )
        self.root_patch.start()
        Workspace.ensure_workspace()
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.temporary_directory.cleanup)

    def test_voice_commands_create_folders_and_navigate_workspace(self):
        window = QMainWindow()
        stack = QStackedWidget(window)
        workspace = WorkspaceScreen()
        stack.addWidget(workspace)
        window.setCentralWidget(stack)

        result = workspace._execute_voice_command(
            "create_folder",
            "Voice Projects",
        )
        folder = self.workspace_root / "3D" / "Voice Projects"

        self.assertTrue(folder.is_dir())
        self.assertEqual(result, "Created the folder Voice Projects.")
        self.assertEqual(
            workspace._execute_voice_command("open_project", "Voice Projects"),
            "Opened the folder Voice Projects.",
        )
        self.assertEqual(workspace.current_folder.resolve(), folder.resolve())
        workspace.close()
        window.close()

    def test_voice_created_design_switches_from_circuits_and_loads_hologram(self):
        window = QMainWindow()
        stack = QStackedWidget(window)
        workspace = WorkspaceScreen()
        stack.addWidget(workspace)
        window.setCentralWidget(stack)
        self.addCleanup(window.close)
        self.addCleanup(workspace.close)
        self.addCleanup(workspace.refresh_timer.stop)
        workspace._change_project_type("Circuits")

        with (
            patch.object(
                Workspace,
                "generate_design_parts",
                return_value=[{
                    "name": "Seat",
                    "shape": "box",
                    "position": [0.0, 0.0, 0.0],
                    "size": [1.0, 1.0, 1.0],
                }],
            ),
            patch.object(
                Workspace,
                "load_mesh_for_workbench",
                return_value=(
                    [((0, 0, 0), (1, 0, 0), (0, 1, 0))],
                    None,
                ),
            ),
        ):
            result = workspace._execute_voice_command(
                "create",
                "chair for a 3D printer",
            )
            self.assertTrue(QThreadPool.globalInstance().waitForDone(3000))
            self.app.processEvents()

        created_path = self.workspace_root / "3D" / "chair for a 3D printer.aiko3d"
        self.assertTrue(created_path.is_file())
        self.assertEqual(workspace.project_type, "3D")
        self.assertIn("added it to the workbench", result)
        self.assertEqual(len(workspace._workbench_items), 1)
        self.assertEqual(
            Path(workspace._workbench_items[0]["path"]).resolve(),
            created_path.resolve(),
        )

    def test_workspace_snapshot_includes_folder_files_and_workbench_items(self):
        design_path = self.workspace_root / "3D" / "desk lamp.aiko3d"
        Workspace.save_design(design_path, {
            "name": "desk lamp",
            "parts": [{
                "name": "Base",
                "shape": "cylinder",
                "position": [0.0, 0.0, 0.0],
                "size": [1.0, 1.0, 1.0],
            }],
        })
        nested_folder = Workspace.create_folder("Prototype Parts")
        (nested_folder / "notes.txt").write_text("test", encoding="utf-8")
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        screen._workbench_items = [{"name": "desk lamp", "path": str(design_path)}]
        screen.viewer.selected_workbench_item = 0

        snapshot = screen._execute_voice_command("describe", "")

        self.assertIn("3D Designs:", snapshot)
        self.assertIn("Prototype Parts (folder)", snapshot)
        self.assertIn("Prototype Parts\\notes.txt", snapshot)
        self.assertIn("Workbench holograms:", snapshot)
        self.assertIn("desk lamp (selected)", snapshot)
        self.assertIn("parts: Base", snapshot)

    def test_workspace_shows_aiko_status_without_conversation_orbs(self):
        workspace = WorkspaceScreen()
        self.addCleanup(workspace.close)
        workspace.show()
        self.app.processEvents()
        self.assertTrue(workspace.assistant_status_panel.isVisible())
        self.assertEqual(
            workspace.assistant_status_panel.aiko_core.width(),
            104,
        )
        self.assertLess(
            workspace.assistant_status_panel.y(),
            workspace.height()
            - workspace.assistant_status_panel.height()
            - 24,
        )
        for status in ("Listening...", "Executing Task...", "Answering..."):
            with self.subTest(status=status):
                with (
                    patch("frontend.GUI.GetAssistantStatus", return_value=status),
                    patch("frontend.GUI.GetMicrophoneStatus", return_value="True"),
                ):
                    workspace._refresh_assistant_status()
                self.assertEqual(
                    workspace.assistant_status_panel.assistant_status_label.text(),
                    status,
                )
                self.assertEqual(
                    workspace.assistant_status_panel.microphone_status_label.text(),
                    "MIC ON",
                )
                self.assertEqual(
                    workspace.assistant_status_panel.aiko_core.is_responding,
                    status == "Answering...",
                )
        SetSpeechLevel(0.7)
        self.assertEqual(
            workspace.assistant_status_panel.aiko_core.speech_level,
            0.7,
        )
        with (
            patch("frontend.GUI.GetAssistantStatus", return_value="Available..."),
            patch("frontend.GUI.GetMicrophoneStatus", return_value="False"),
        ):
            workspace._refresh_assistant_status()
        self.assertEqual(
            workspace.assistant_status_panel.microphone_status_label.text(),
            "MIC OFF",
        )
        self.assertEqual(workspace.findChildren(OrbMapCanvas), [])
        workspace.close()

    def test_map_refresh_and_animation_timers_pause_when_page_is_hidden(self):
        screen = ConversationMapScreen()
        self.addCleanup(screen.close)
        screen.show()
        self.app.processEvents()

        self.assertTrue(screen.refresh_timer.isActive())
        self.assertTrue(screen.rotation_timer.isActive())
        self.assertTrue(screen.status_timer.isActive())
        self.assertTrue(screen.reminder_panel.refresh_timer.isActive())

        screen.hide()

        self.assertFalse(screen.refresh_timer.isActive())
        self.assertFalse(screen.rotation_timer.isActive())
        self.assertFalse(screen.status_timer.isActive())
        self.assertFalse(screen.reminder_panel.refresh_timer.isActive())

    def test_breaking_news_panel_uses_its_updated_dark_blue_theme(self):
        panel = BreakingNewsPanel()

        self.assertIn("#101827", panel.styleSheet())
        self.assertIn("#ff657a", panel.findChild(QLabel).styleSheet())

    def test_reminder_notification_can_be_dragged_with_left_mouse_button(self):
        notification = ReminderNotification({"id": "test", "title": "Call Sam"})
        self.addCleanup(notification.close)
        notification.move(50, 50)
        notification.show()
        self.app.processEvents()

        def event(button, buttons, global_position):
            return SimpleNamespace(
                button=lambda: button,
                buttons=lambda: buttons,
                globalPos=lambda: global_position,
                accept=lambda: None,
            )

        notification.mousePressEvent(
            event(Qt.LeftButton, Qt.LeftButton, QPoint(60, 65))
        )
        notification.mouseMoveEvent(
            event(Qt.NoButton, Qt.LeftButton, QPoint(90, 95))
        )

        self.assertEqual(notification.pos(), QPoint(80, 80))

        notification.mouseReleaseEvent(
            event(Qt.LeftButton, Qt.NoButton, QPoint(90, 95))
        )
        self.assertIsNone(notification._drag_offset)

    def test_workspace_file_list_is_not_draggable_and_single_click_opens_folder(self):
        folder = Workspace.create_folder("Design files")
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen._refresh_projects()
        item = screen.project_list.item(0)

        self.assertEqual(
            screen.project_list.dragDropMode(),
            QAbstractItemView.NoDragDrop,
        )
        self.assertFalse(screen.project_list.dragEnabled())
        self.assertFalse(screen.project_list.acceptDrops())
        self.assertFalse(item.flags() & Qt.ItemIsDragEnabled)
        self.assertFalse(item.flags() & Qt.ItemIsDropEnabled)

        screen.project_list.itemClicked.emit(item)

        self.assertEqual(screen.current_folder.resolve(), folder.resolve())

    def test_workspace_hand_pinch_opens_item_on_first_click(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        stack = SimpleNamespace(currentWidget=lambda: screen)
        window = SimpleNamespace(
            centralWidget=lambda: stack,
            workspace_screen=screen,
        )
        target = screen.project_list.viewport()
        pinch_state = {
            "target": target,
            "position": QPoint(20, 20),
            "start_position": QPoint(20, 20),
            "pinch_started_at": 1.0,
            "moved": False,
            "fist_seen": False,
            "mode": "candidate",
            "pressed": False,
        }
        hand_screen = SimpleNamespace(
            window=lambda: window,
            _hand_gesture_states={"single": pinch_state},
            _pending_hand_clicks={},
            _send_hand_pointer_click=Mock(),
            _workspace_click_target=lambda widget: (
                ConversationMapScreen._workspace_click_target(
                    hand_screen, widget
                )
            ),
        )

        with patch("frontend.GUI.time.monotonic", return_value=1.1):
            ConversationMapScreen._update_hand_interaction(
                hand_screen,
                "single",
                (0.0, 0.0, 0.4, 0.5, False, 0, 0.0, 0.0),
                QPoint(20, 20),
                pinched=False,
            )

        hand_screen._send_hand_pointer_click.assert_called_once_with(
            target, QPoint(20, 20)
        )
        self.assertEqual(hand_screen._pending_hand_clicks, {})

    def test_opening_a_model_loads_mesh_without_blocking_the_ui(self):
        source = Path(self.temporary_directory.name) / "sample.obj"
        source.write_text(
            "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
            encoding="utf-8",
        )
        Workspace.import_project(source)
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen._refresh_projects()
        item = screen.project_list.item(0)
        load_started = threading.Event()
        finish_loading = threading.Event()
        self.addCleanup(finish_loading.set)

        def delayed_mesh_load(_path):
            load_started.set()
            if not finish_loading.wait(2):
                raise TimeoutError("Test mesh load was not released.")
            return [((0, 0, 0), (1, 0, 0), (0, 1, 0))]

        with patch.object(
            Workspace,
            "load_mesh_for_workbench",
            side_effect=lambda path: (delayed_mesh_load(path), None),
        ):
            screen.project_list.itemClicked.emit(item)
            self.assertTrue(load_started.wait(1))
            self.assertEqual(screen.status_label.text(), "Opening sample...")
            finish_loading.set()
            self.assertTrue(QThreadPool.globalInstance().waitForDone(3000))
            self.app.processEvents()

        self.assertEqual(len(screen.viewer.triangles), 1)
        self.assertEqual(
            screen.status_label.text(),
            "Workbench: 1 project(s). Added sample.",
        )
        self.assertFalse(screen.viewer.circuit_mode)
        self.assertAlmostEqual(screen.viewer.auto_fit_zoom, 1.0)

    def test_workbench_adds_models_side_by_side_and_fits_the_scene(self):
        large_mesh = [((-2, -1, 0), (2, -1, 0), (0, 1, 0))]
        small_mesh = [((-0.5, -0.25, 0), (0.5, -0.25, 0), (0, 0.25, 0))]

        (
            triangles,
            materials,
            triangle_owners,
            fit_zoom,
            scene_center,
            has_circuit,
        ) = (
            WorkspaceScreen._compose_workbench_mesh([
                {
                    "triangles": large_mesh,
                    "materials": None,
                    "is_circuit": False,
                    "offset": [0.0, 0.0, 0.0],
                    "group_id": 1,
                },
                {
                    "triangles": small_mesh,
                    "materials": None,
                    "is_circuit": False,
                    "offset": [0.0, 0.0, 0.0],
                    "group_id": 2,
                },
            ])
        )

        self.assertEqual(len(triangles), 2)
        self.assertEqual(materials, ["model", "model"])
        self.assertEqual(triangle_owners, [0, 1])
        self.assertGreater(fit_zoom, 0.7)
        self.assertLessEqual(fit_zoom, 1.0)
        self.assertGreater(scene_center[0], 0.0)
        self.assertEqual(scene_center[1:], (0.0, 0.0))
        self.assertFalse(has_circuit)
        first_left = min(vertex[0] for vertex in triangles[0])
        first_width = max(vertex[0] for vertex in triangles[0]) - min(
            vertex[0] for vertex in triangles[0]
        )
        second_left = min(vertex[0] for vertex in triangles[1])
        first_right = first_left + first_width
        second_width = max(vertex[0] for vertex in triangles[1]) - min(
            vertex[0] for vertex in triangles[1]
        )
        self.assertAlmostEqual(first_width / second_width, 4)
        self.assertAlmostEqual(first_right, second_left)
        self.assertAlmostEqual(
            (min(vertex[1] for vertex in triangles[0])
             + max(vertex[1] for vertex in triangles[0])) / 2,
            (min(vertex[1] for vertex in triangles[1])
             + max(vertex[1] for vertex in triangles[1])) / 2,
        )
        self.assertAlmostEqual(
            (min(vertex[2] for vertex in triangles[0])
             + max(vertex[2] for vertex in triangles[0])) / 2,
            (min(vertex[2] for vertex in triangles[1])
             + max(vertex[2] for vertex in triangles[1])) / 2,
        )
        self.assertEqual(
            len(WorkspaceScreen._compose_workbench_mesh([])),
            6,
        )

    def test_adding_a_larger_model_preserves_the_first_models_world_size(self):
        first = self._make_workbench_item(1)
        first["triangles"] = [
            ((-0.5, 0, 0), (0.5, 0, 0), (0, 0.5, 0))
        ]
        larger = self._make_workbench_item(2)
        larger["triangles"] = [
            ((-10, 0, 0), (10, 0, 0), (0, 10, 0))
        ]

        one_model = WorkspaceScreen._compose_workbench_mesh([first])
        two_models = WorkspaceScreen._compose_workbench_mesh([first, larger])

        first_width_alone = max(
            vertex[0] for vertex in one_model[0][0]
        ) - min(vertex[0] for vertex in one_model[0][0])
        first_width_together = max(
            vertex[0] for vertex in two_models[0][0]
        ) - min(vertex[0] for vertex in two_models[0][0])
        self.assertAlmostEqual(first_width_alone, first_width_together)
        self.assertLess(two_models[3], 0.1)

    @staticmethod
    def _make_workbench_item(index):
        return {
            "path": f"part-{index}.obj",
            "name": f"part-{index}",
            "triangles": [
                ((-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.0, 0.5, 0.0))
            ],
            "materials": None,
            "is_circuit": False,
            "offset": [0.0, 0.0, 0.0],
            "scale": 1.0,
            "rotation": [0.0, 0.0, 0.0],
            "group_id": index,
        }

    def test_move_mode_dragging_a_hologram_moves_only_the_selected_part(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        original_center = (0.0, 0.0, 0.0)
        screen._workbench_items = [
            self._make_workbench_item(1),
            self._make_workbench_item(2),
        ]
        self.assertFalse(screen.rotate_items_button.isChecked())
        screen._refresh_workbench(reset_zoom=True, update_camera=True)
        screen.viewer.rotation = 0.0
        screen.viewer.vertical_rotation = 0.0
        screen.viewer.rotation_timer.stop()

        projected = screen.viewer._project_current_mesh()
        first_triangle = screen.viewer._mesh_triangles[0]
        point = QPoint(
            round(sum(projected[index][0].x() for index in first_triangle) / 3),
            round(sum(projected[index][0].y() for index in first_triangle) / 3),
        )
        self.assertEqual(screen.viewer._workbench_item_at(point), 0)
        mesh_triangles = screen.viewer._mesh_triangles
        projected_before_drag = screen.viewer._project_current_mesh()

        screen.viewer.mousePressEvent(SimpleNamespace(
            button=lambda: Qt.LeftButton,
            pos=lambda: point,
        ))
        screen.viewer.mouseMoveEvent(SimpleNamespace(
            pos=lambda: point + QPoint(18, -12),
        ))
        screen.viewer.mouseReleaseEvent(SimpleNamespace(
            button=lambda: Qt.LeftButton,
        ))

        self.assertNotEqual(
            screen._workbench_items[0]["offset"],
            [0.0, 0.0, 0.0],
        )
        self.assertEqual(
            screen._workbench_items[1]["offset"],
            [0.0, 0.0, 0.0],
        )
        self.assertIs(screen.viewer._mesh_triangles, mesh_triangles)
        self.assertNotEqual(
            screen.viewer._project_current_mesh(),
            projected_before_drag,
        )
        self.assertEqual(screen.viewer.focused_workbench_item, 0)
        self.assertNotEqual(screen.viewer.scene_center, original_center)

    def test_hand_drag_rotates_item_without_moving_its_position(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen.rotate_items_button.setChecked(True)
        screen._workbench_items = [
            self._make_workbench_item(1),
        ]
        screen._refresh_workbench(reset_zoom=True, update_camera=True)
        screen.viewer.rotation = 0.0
        screen.viewer.vertical_rotation = 0.0
        screen.viewer.rotation_timer.stop()

        projected = screen.viewer._project_current_mesh()
        triangle = screen.viewer._mesh_triangles[0]
        grab_point = QPoint(
            round(sum(projected[index][0].x() for index in triangle) / 3),
            round(sum(projected[index][0].y() for index in triangle) / 3),
        )
        screen.viewer.set_hand_drag_active(True)
        original_offset = screen._workbench_items[0]["offset"][:]
        screen.viewer.mousePressEvent(SimpleNamespace(
            button=lambda: Qt.LeftButton,
            pos=lambda: grab_point,
        ))
        rotation_width = screen.viewer._hand_rotation_screen_width
        rotation_height = screen.viewer._hand_rotation_screen_height
        target = grab_point - QPoint(round(rotation_width / 2), 0)
        screen.viewer.mouseMoveEvent(SimpleNamespace(pos=lambda: target))

        self.assertAlmostEqual(
            screen._workbench_items[0]["rotation"][1],
            math.pi / 2,
            places=2,
        )
        self.assertEqual(screen._workbench_items[0]["offset"], original_offset)

        final_target = target - QPoint(0, round(rotation_height / 2))
        screen.viewer.mouseMoveEvent(SimpleNamespace(pos=lambda: final_target))
        self.assertAlmostEqual(
            screen._workbench_items[0]["rotation"][1],
            math.pi / 2,
            places=2,
        )
        self.assertAlmostEqual(
            screen._workbench_items[0]["rotation"][0],
            0.0,
            places=2,
        )
        self.assertEqual(screen._workbench_items[0]["offset"], original_offset)

        screen.viewer.mouseReleaseEvent(SimpleNamespace(
            button=lambda: Qt.LeftButton,
        ))
        screen.viewer.set_hand_drag_active(False)

    def test_dense_workbench_mesh_limits_drawn_faces_but_keeps_full_mesh(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        item = self._make_workbench_item(1)
        item["triangles"] *= 4501
        screen._workbench_items = [item]

        screen._refresh_workbench(reset_zoom=True, update_camera=True)

        self.assertEqual(len(screen.viewer._mesh_triangles), 4501)
        self.assertLessEqual(
            len(screen.viewer._render_triangle_indices),
            screen.viewer.MAX_RENDERED_TRIANGLES,
        )
        self.assertFalse(screen.viewer.rotation_timer.isActive())

    def test_workbench_preview_keeps_smaller_meshes_at_full_detail(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        simple = self._make_workbench_item(1)
        dense = self._make_workbench_item(2)
        dense["triangles"] *= 10
        screen._workbench_items = [dense, simple]
        screen.viewer.MAX_RENDERED_TRIANGLES = 6

        screen._refresh_workbench(reset_zoom=True, update_camera=True)

        selected_owners = {
            screen.viewer.workbench_triangle_owners[index]
            for index in screen.viewer._render_triangle_indices
        }
        selected_simple_faces = sum(
            screen.viewer.workbench_triangle_owners[index] == 1
            for index in screen.viewer._render_triangle_indices
        )
        self.assertIn(1, selected_owners)
        self.assertEqual(selected_simple_faces, 1)
        self.assertLessEqual(
            len(screen.viewer._render_triangle_indices),
            screen.viewer.MAX_RENDERED_TRIANGLES,
        )

    def test_cached_workbench_transforms_match_composed_geometry(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        first = self._make_workbench_item(1)
        second = self._make_workbench_item(2)
        first["group_id"] = second["group_id"] = 1
        first["offset"] = [0.1, -0.2, 0.3]
        second["offset"] = [-0.1, 0.2, -0.3]
        first["scale"] = second["scale"] = 1.4
        first["rotation"] = second["rotation"] = [0.2, -0.1, 0.3]
        items = [first, second]
        _dimensions, centers, base_centers, unit_scale = (
            WorkspaceScreen._workbench_layout(items)
        )

        screen.viewer.set_workbench_mesh(
            items, centers, base_centers, unit_scale
        )
        composed_triangles = WorkspaceScreen._compose_workbench_mesh(items)[0]
        world_vertices = screen.viewer._workbench_world_vertices()

        for triangle, composed_triangle in zip(
            screen.viewer._mesh_triangles, composed_triangles
        ):
            for vertex_index, expected in zip(triangle, composed_triangle):
                for actual_coordinate, expected_coordinate in zip(
                    world_vertices[vertex_index], expected
                ):
                    self.assertAlmostEqual(
                        actual_coordinate, expected_coordinate
                    )

    def test_rotate_mode_rotates_a_hologram_without_moving_it(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen._workbench_items = [
            self._make_workbench_item(1),
            self._make_workbench_item(2),
        ]
        screen._refresh_workbench(reset_zoom=True, update_camera=True)
        screen.viewer.rotation = 0.0
        screen.viewer.vertical_rotation = 0.0
        screen.viewer.rotation_timer.stop()
        projected = screen.viewer._project_current_mesh()
        first_triangle = screen.viewer._mesh_triangles[0]
        point = QPoint(
            round(sum(projected[index][0].x() for index in first_triangle) / 3),
            round(sum(projected[index][0].y() for index in first_triangle) / 3),
        )
        original_offset = screen._workbench_items[0]["offset"][:]
        projected_before_rotation = screen.viewer._project_current_mesh()

        screen.rotate_items_button.setChecked(True)
        self.assertTrue(screen.rotate_items_button.isChecked())
        screen.viewer.mousePressEvent(SimpleNamespace(
            button=lambda: Qt.LeftButton,
            pos=lambda: point,
        ))
        screen.viewer.mouseMoveEvent(SimpleNamespace(
            pos=lambda: point + QPoint(40, -30),
        ))
        screen.viewer.mouseReleaseEvent(SimpleNamespace(
            button=lambda: Qt.LeftButton,
        ))

        self.assertEqual(screen._workbench_items[0]["offset"], original_offset)
        self.assertAlmostEqual(
            screen._workbench_items[0]["rotation"][0],
            -0.3,
        )
        self.assertAlmostEqual(
            screen._workbench_items[0]["rotation"][1],
            0.4,
        )
        self.assertEqual(
            screen._workbench_items[0]["offset"],
            [0.0, 0.0, 0.0],
        )
        self.assertNotEqual(
            screen.viewer._project_current_mesh(),
            projected_before_rotation,
        )

        screen._rotate_workbench_item(0, 0.0, 0.0, 2 * math.pi)
        self.assertAlmostEqual(
            screen._workbench_items[0]["rotation"][2],
            2 * math.pi,
        )

    def test_dragging_empty_workbench_orbits_view_without_moving_holograms(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen._workbench_items = [self._make_workbench_item(1)]
        screen._refresh_workbench(reset_zoom=True, update_camera=True)
        screen.viewer.rotation = 0.0
        screen.viewer.vertical_rotation = 0.0
        screen.viewer.rotation_timer.stop()
        original_offset = screen._workbench_items[0]["offset"][:]

        screen.viewer.mousePressEvent(SimpleNamespace(
            button=lambda: Qt.LeftButton,
            pos=lambda: QPoint(10, 10),
        ))
        screen.viewer.mouseMoveEvent(SimpleNamespace(
            pos=lambda: QPoint(45, 28),
        ))
        screen.viewer.mouseReleaseEvent(SimpleNamespace(
            button=lambda: Qt.LeftButton,
        ))

        self.assertAlmostEqual(screen.viewer.rotation, -35 * 0.0032)
        self.assertAlmostEqual(screen.viewer.vertical_rotation, 18 * 0.0032)
        self.assertEqual(
            screen._workbench_items[0]["offset"],
            original_offset,
        )

    def test_new_hologram_spawns_touching_the_rightmost_moved_hologram(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        first = self._make_workbench_item(1)
        first["reference_size"] = 1.0
        first["fit_scale"] = 1.0
        first["vertices"] = {
            tuple(vertex)
            for triangle in first["triangles"]
            for vertex in triangle
        }
        first["offset"] = [0.0, 0.25, 0.4]
        screen._workbench_items = [first]
        screen._refresh_workbench(reset_zoom=True, update_camera=True)
        second = self._make_workbench_item(2)
        second["reference_size"] = 1.0
        second["fit_scale"] = 1.0
        second["vertices"] = {
            tuple(vertex)
            for triangle in second["triangles"]
            for vertex in triangle
        }

        screen._place_new_workbench_item(second)
        combined, *_ = WorkspaceScreen._compose_workbench_mesh([
            first,
            second,
        ])
        first_vertices = [vertex for triangle in combined[:1] for vertex in triangle]
        second_vertices = [
            vertex for triangle in combined[1:] for vertex in triangle
        ]

        self.assertAlmostEqual(
            max(vertex[0] for vertex in first_vertices),
            min(vertex[0] for vertex in second_vertices),
        )
        for axis in (1, 2):
            first_center = (
                min(vertex[axis] for vertex in first_vertices)
                + max(vertex[axis] for vertex in first_vertices)
            ) / 2
            second_center = (
                min(vertex[axis] for vertex in second_vertices)
                + max(vertex[axis] for vertex in second_vertices)
            ) / 2
            self.assertAlmostEqual(first_center, second_center)

        third = self._make_workbench_item(3)
        third["reference_size"] = 1.0
        third["fit_scale"] = 1.0
        third["vertices"] = {
            tuple(vertex)
            for triangle in third["triangles"]
            for vertex in triangle
        }
        screen._workbench_items = [first, second]
        screen._refresh_workbench(reset_zoom=True, update_camera=True)
        screen._place_new_workbench_item(third)
        all_triangles, *_ = WorkspaceScreen._compose_workbench_mesh([
            first,
            second,
            third,
        ])
        existing_vertices = [
            vertex
            for triangle in all_triangles[:2]
            for vertex in triangle
        ]
        third_vertices = [
            vertex for triangle in all_triangles[2:] for vertex in triangle
        ]
        self.assertAlmostEqual(
            max(vertex[0] for vertex in existing_vertices),
            min(vertex[0] for vertex in third_vertices),
        )
        for axis in (1, 2):
            existing_center = (
                min(vertex[axis] for vertex in existing_vertices)
                + max(vertex[axis] for vertex in existing_vertices)
            ) / 2
            third_center = (
                min(vertex[axis] for vertex in third_vertices)
                + max(vertex[axis] for vertex in third_vertices)
            ) / 2
            self.assertAlmostEqual(existing_center, third_center)

    def test_snap_combine_places_moved_holograms_in_touching_contact(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen._workbench_items = [
            self._make_workbench_item(1),
            self._make_workbench_item(2),
        ]
        screen._workbench_items[1]["offset"] = [0.5, 0.15, 0.0]
        screen.viewer.selected_workbench_item = 1
        screen._refresh_workbench(reset_zoom=True, update_camera=True)

        screen._combine_holograms()

        (first_center, first_half), (second_center, second_half) = (
            screen._workbench_item_bounds(0)[1]
        )
        self.assertAlmostEqual(
            abs(second_center[0] - first_center[0]),
            first_half[0] + second_half[0],
        )
        self.assertLess(
            abs(second_center[1] - first_center[1]),
            first_half[1] + second_half[1],
        )
        self.assertEqual(
            screen._workbench_items[0]["group_id"],
            screen._workbench_items[1]["group_id"],
        )

    def test_snap_uses_the_bounds_of_the_whole_connected_assembly(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        first, second, third = (
            self._make_workbench_item(index) for index in (1, 2, 3)
        )
        first["group_id"] = second["group_id"] = 1
        third["offset"] = [1.0, 0.2, 0.0]
        screen._workbench_items = [first, second, third]
        screen.viewer.selected_workbench_item = 1
        screen._refresh_workbench(reset_zoom=True, update_camera=True)

        screen._combine_holograms()

        bounds = screen._workbench_item_bounds(0)[1]
        (assembly_center, assembly_half), (third_center, third_half) = (
            screen._combined_bounds((0, 1), bounds),
            bounds[2],
        )
        self.assertAlmostEqual(
            assembly_center[0] + assembly_half[0],
            third_center[0] - third_half[0],
        )
        self.assertEqual(
            {item["group_id"] for item in screen._workbench_items},
            {third["group_id"]},
        )

    def test_two_hand_pinching_drags_and_resizes_a_hologram(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen.resize(1000, 700)
        screen._workbench_items = [self._make_workbench_item(1)]
        screen._refresh_workbench(reset_zoom=True, update_camera=True)
        screen.viewer.resize(600, 500)
        screen.viewer.rotation = 0.0
        screen.viewer.vertical_rotation = 0.0
        screen.viewer.rotation_timer.stop()
        projected = screen.viewer._project_current_mesh()
        first_triangle = screen.viewer._mesh_triangles[0]
        center = QPoint(
            round(sum(projected[index][0].x() for index in first_triangle) / 3),
            round(sum(projected[index][0].y() for index in first_triangle) / 3),
        )
        positions = [center + QPoint(-8, 0), center + QPoint(8, 0)]

        self.assertTrue(
            screen.viewer.begin_two_hand_item_manipulation(positions)
        )
        self.assertTrue(
            screen.viewer.update_two_hand_item_manipulation([
                position + QPoint(12, -6)
                for position in positions
            ])
        )
        self.assertNotEqual(
            screen._workbench_items[0]["offset"],
            [0.0, 0.0, 0.0],
        )
        self.assertAlmostEqual(screen._workbench_items[0]["scale"], 1.0)

        self.assertTrue(
            screen.viewer.update_two_hand_item_manipulation([
                center + QPoint(-12, 0),
                center + QPoint(12, 0),
            ])
        )
        self.assertGreater(screen._workbench_items[0]["scale"], 1.0)
        expanded_scale = screen._workbench_items[0]["scale"]
        self.assertTrue(
            screen.viewer.update_two_hand_item_manipulation([
                center + QPoint(-4, 0),
                center + QPoint(4, 0),
            ])
        )
        self.assertLess(screen._workbench_items[0]["scale"], expanded_scale)
        screen.viewer.update_two_hand_item_manipulation([
            center + QPoint(0, -8),
            center + QPoint(0, 8),
        ])
        self.assertNotEqual(
            screen._workbench_items[0]["rotation"][2],
            0.0,
        )
        before_depth_move = screen._workbench_items[0]["offset"][2]
        screen.viewer.update_two_hand_item_manipulation([
            center + QPoint(0, -8),
            center + QPoint(0, 8),
        ], depth_delta=0.02)
        self.assertAlmostEqual(
            screen._workbench_items[0]["offset"][2],
            before_depth_move + 0.1,
        )
        screen.viewer.update_two_hand_item_manipulation([
            center + QPoint(0, -8),
            center + QPoint(0, 8),
        ], depth_delta=-0.02)
        self.assertAlmostEqual(
            screen._workbench_items[0]["offset"][2],
            before_depth_move,
        )
        screen.viewer.end_two_hand_item_manipulation()
        self.assertIsNone(screen.viewer._two_hand_item_index)

    def test_one_hand_pinch_drag_pushes_and_pulls_hologram_depth(self):
        workspace = WorkspaceScreen()
        self.addCleanup(workspace.close)
        self.addCleanup(workspace.refresh_timer.stop)
        workspace._workbench_items = [self._make_workbench_item(1)]
        workspace._refresh_workbench(reset_zoom=True, update_camera=True)
        workspace.viewer.rotation = 0.0
        workspace.viewer.vertical_rotation = 0.0
        workspace.viewer.dragged_workbench_item = 0
        hand_state = {
            "target": workspace.viewer,
            "mode": "grab",
            "depth_hand_size": 0.3,
        }
        hand_screen = SimpleNamespace(
            _hand_gesture_states={"single": hand_state},
            window=lambda: SimpleNamespace(workspace_screen=workspace),
        )

        ConversationMapScreen._update_single_hand_workbench_depth(
            hand_screen, (0, 0, 0, 0, False, 0, 0, 0, 0.33), True
        )
        self.assertAlmostEqual(
            workspace._workbench_items[0]["offset"][2],
            1.5 * math.log(0.33 / 0.3),
        )

        ConversationMapScreen._update_single_hand_workbench_depth(
            hand_screen, (0, 0, 0, 0, False, 0, 0, 0, 0.3), True
        )
        self.assertAlmostEqual(
            workspace._workbench_items[0]["offset"][2],
            0.0,
        )

    def test_workbench_actions_snap_remove_and_clear_without_merging_files(self):
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen._workbench_items = [
            self._make_workbench_item(1),
            self._make_workbench_item(2),
        ]
        source_triangles = [
            item["triangles"] for item in screen._workbench_items
        ]
        screen.viewer.selected_workbench_item = 1
        screen._refresh_workbench(reset_zoom=True, update_camera=True)
        self.assertFalse(screen.workbench_actions.isHidden())

        screen._combine_holograms()

        self.assertEqual(
            screen._workbench_items[0]["group_id"],
            screen._workbench_items[1]["group_id"],
        )
        self.assertEqual(
            screen._workbench_items[1]["offset"],
            [0.0, 0.0, 0.0],
        )
        self.assertEqual(
            [item["triangles"] for item in screen._workbench_items],
            source_triangles,
        )
        first_offset = screen._workbench_items[0]["offset"][:]
        second_offset = screen._workbench_items[1]["offset"][:]
        screen._move_workbench_item(0, 0.2, 0.1, 0.3)
        self.assertEqual(
            screen._workbench_items[0]["offset"],
            [first_offset[0] + 0.2, first_offset[1] + 0.1, first_offset[2] + 0.3],
        )
        self.assertEqual(
            screen._workbench_items[1]["offset"],
            [second_offset[0] + 0.2, second_offset[1] + 0.1, second_offset[2] + 0.3],
        )

        screen.viewer.focused_workbench_item = 1
        screen.viewer.selected_workbench_item = 1
        screen._remove_last_hologram()
        self.assertEqual(len(screen._workbench_items), 1)
        self.assertIsNone(screen.viewer.focused_workbench_item)
        self.assertEqual(screen.viewer.selected_workbench_item, 0)
        self.assertFalse(screen.workbench_actions.isHidden())
        screen._workbench_items.append(self._make_workbench_item(3))
        screen._refresh_workbench()
        self.assertFalse(screen.workbench_actions.isHidden())
        screen._clear_workbench()
        self.assertEqual(screen._workbench_items, [])
        self.assertEqual(screen.viewer.triangles, [])
        self.assertTrue(screen.workbench_actions.isHidden())

    def test_workbench_holograms_match_the_first_loaded_model_size(self):
        first = self._make_workbench_item(1)
        second = self._make_workbench_item(2)
        first["triangles"] = [
            ((-1, -1, -1), (1, -1, -1), (0, 1, 1))
        ]
        second["triangles"] = [
            ((-5, -5, -5), (5, -5, -5), (0, 5, 5))
        ]
        first["vertices"] = {
            vertex for triangle in first["triangles"] for vertex in triangle
        }
        second["vertices"] = {
            vertex for triangle in second["triangles"] for vertex in triangle
        }
        first["reference_size"] = 2
        first["fit_scale"] = 1
        second["reference_size"] = 2
        second["fit_scale"] = 0.2

        composed, *_ = WorkspaceScreen._compose_workbench_mesh([first, second])
        first_extent = max(
            max(vertex[axis] for triangle in composed[:1] for vertex in triangle)
            - min(vertex[axis] for triangle in composed[:1] for vertex in triangle)
            for axis in range(3)
        )
        second_extent = max(
            max(vertex[axis] for triangle in composed[1:] for vertex in triangle)
            - min(vertex[axis] for triangle in composed[1:] for vertex in triangle)
            for axis in range(3)
        )

        self.assertAlmostEqual(first_extent, second_extent)

    def test_clicking_a_hologram_focuses_then_clicking_out_saves_it(self):
        source = Path(self.temporary_directory.name) / "focus.obj"
        source.write_text(
            "v -1 -1 0\nv 1 -1 0\nv 0 1 0\nf 1 2 3\n",
            encoding="utf-8",
        )
        project = Workspace.import_project(source)
        triangles, materials = Workspace.load_mesh_for_workbench(project)
        prepared_mesh = HologramCanvas.prepare_mesh(triangles)
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen.viewer.resize(500, 400)
        screen._workbench_items = [{
            "path": str(project),
            "name": project.stem,
            "triangles": triangles,
            "prepared_mesh": (
                (*prepared_mesh, materials)
                if materials is not None
                else prepared_mesh
            ),
            "vertices": prepared_mesh[1],
            "materials": materials,
            "is_circuit": False,
            "offset": [0.0, 0.0, 0.0],
            "scale": 1.0,
            "rotation": [0.0, 0.0, 0.0],
            "reference_size": 2.0,
            "fit_scale": 1.0,
            "group_id": 1,
        }]
        screen._refresh_workbench(reset_zoom=True, update_camera=True)
        screen.viewer.rotation = 0.0
        screen.viewer.vertical_rotation = 0.0
        projected = screen.viewer._project_current_mesh()
        triangle = screen.viewer._mesh_triangles[0]
        point = QPoint(
            round(sum(projected[index][0].x() for index in triangle) / 3),
            round(sum(projected[index][0].y() for index in triangle) / 3),
        )

        QTest.mouseClick(screen.viewer, Qt.LeftButton, pos=point)

        self.assertEqual(screen.viewer.focused_workbench_item, 0)
        screen._scale_selected_workbench_item(0.9)
        QTest.mouseClick(
            screen.viewer,
            Qt.LeftButton,
            pos=QPoint(screen.viewer.width() - 2, screen.viewer.height() - 2),
        )

        self.assertIsNone(screen.viewer.focused_workbench_item)
        saved = Workspace.load_workbench_transform(project)
        self.assertAlmostEqual(saved["scale"], 0.9)

    def test_opening_multiple_workspace_models_keeps_them_in_the_workbench(self):
        project_paths = []
        for name in ("gear.obj", "track.obj"):
            source = Path(self.temporary_directory.name) / name
            source.write_text(
                "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n",
                encoding="utf-8",
            )
            project_paths.append(Workspace.import_project(source))

        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen._refresh_projects()
        meshes = {
            "gear.obj": [((-2, -1, 0), (2, -1, 0), (0, 1, 0))],
            "track.obj": [((-0.5, -0.25, 0), (0.5, -0.25, 0), (0, 0.25, 0))],
        }

        def load_project(path):
            return meshes[Path(path).name], None

        with patch.object(
            Workspace,
            "load_mesh_for_workbench",
            side_effect=load_project,
        ):
            for index in range(screen.project_list.count()):
                screen.project_list.itemClicked.emit(
                    screen.project_list.item(index)
                )
            self.assertTrue(QThreadPool.globalInstance().waitForDone(3000))
            self.app.processEvents()

        self.assertEqual(len(screen._workbench_items), 2)
        self.assertEqual(
            {Path(item["path"]).name for item in screen._workbench_items},
            {path.name for path in project_paths},
        )
        self.assertEqual(len(screen.viewer.triangles), 2)
        scene_vertices = screen.viewer._workbench_world_vertices()
        scene_span = max(
            max(vertex[axis] for vertex in scene_vertices)
            - min(vertex[axis] for vertex in scene_vertices)
            for axis in range(3)
        )
        self.assertAlmostEqual(
            screen.viewer.auto_fit_zoom,
            min(1.0, 1.35 / scene_span),
        )
        self.assertEqual(screen.viewer.workbench_item_count, 2)
        initial_rotation = screen.viewer.rotation
        screen.viewer.apply_hand_drag(0.1, 0.05)
        self.assertNotEqual(screen.viewer.rotation, initial_rotation)
        initial_zoom = screen.viewer.zoom
        screen.viewer.set_hand_zoom(0.0)
        self.assertLess(screen.viewer.zoom, initial_zoom)

    def test_opening_an_eagle_circuit_loads_its_hologram(self):
        source = Path(self.temporary_directory.name) / "sample.brd"
        source.write_text("<eagle/>", encoding="utf-8")
        Workspace.import_project(source, "Circuits")
        screen = WorkspaceScreen()
        self.addCleanup(screen.close)
        self.addCleanup(screen.refresh_timer.stop)
        screen._change_project_type("Circuits")
        item = screen.project_list.item(0)

        with patch.object(
            Workspace,
            "load_mesh_for_workbench",
            return_value=(
                [((0, 0, 0), (1, 0, 0), (0, 1, 0))],
                ["board"],
            ),
        ) as load_mesh:
            screen.project_list.itemClicked.emit(item)
            self.assertTrue(QThreadPool.globalInstance().waitForDone(3000))
            self.app.processEvents()

        load_mesh.assert_called_once_with(item.data(Qt.UserRole)["path"])
        self.assertEqual(len(screen.viewer.triangles), 1)
        self.assertIn("Added sample", screen.status_label.text())
        self.assertEqual(screen.viewer.triangle_materials, ["board"])
        self.assertTrue(screen.viewer.circuit_mode)
        self.assertFalse(screen.viewer.grab().isNull())


if __name__ == "__main__":
    unittest.main()
