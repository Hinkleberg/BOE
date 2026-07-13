#!/usr/bin/env python3
"""
Migration plan for full-duplex conversion of all adapters.

Status: COMPREHENSIVE MIGRATION IN PROGRESS

Update (2026-07-13):
  ✓ Web compare mode now uses dual WebBridge endpoints:
    - WebBridge Dev (7507)
    - WebBridge Live (7508)
  ✓ Start command supports: --live-db, --web-dev-port, --web-live-port

Current Full-Duplex (4 adapters):
  ✓ UnrealAdapter (7100)
  ✓ BlenderAdapter (7200)
  ✓ OmniverseConnector (7300)
  ✓ RobloxHTTPAdapter (7400/8000)

Legacy → Full-Duplex Migration (10+ adapters):
  → GodotAdapter (7500) - Game engine, streaming voxel updates
  → Godot4Bridge (7501) - Godot 4.x native bridge
  → O3DEAdapter (7502) - Amazon Lumberyard/O3DE engine
  → UnityAdapter (7503) - Unity Engine integration
  → MilitarySimAdapter (7504) - Military simulation framework (HLA)
  → AVSimAdapter (7505) - Autonomous vehicle simulator
  → ScientificSimAdapter (7506) - Scientific computing integration
  → WebBridge (7507) - Web-based 3D viewer (Three.js, Babylon.js)
  → StarlinkAdapter (7508) - SpaceX Starlink network simulation
  → HLAFederateBridge (7509) - High-Level Architecture federation

Migration Strategy:
1. Each adapter inherits from DuplexAdapter
2. Expose ALL platform-specific commands as _cmd_* handlers
3. Support legacy API alongside new duplex protocol (backward compatibility)
4. Unified port assignment scheme (7100-7509)
5. All adapters bidirectional with Unreal Engine via DPLX protocol

Command Categories per Adapter:

GodotAdapter (7500):
  - load_region, get_viewport, set_viewport_radius
  - spawn_actor, despawn_actor, update_actor
  - cast_ray, query_physics
  - set_material, load_script
  - get_scene_graph, subscribe_to_updates

UnityAdapter (7503):
  - instantiate_prefab, destroy_gameobject
  - set_transform, get_transform
  - apply_force, apply_velocity
  - instantiate_particle_system, play_sound
  - load_scene, unload_scene
  - get_collider_info, raycast_physics

O3DEAdapter (7502):
  - spawn_entity, destroy_entity
  - apply_physics, set_collider
  - load_asset, unload_asset
  - script_invoke, event_dispatch
  - get_viewport_data

MilitarySimAdapter (7504):
  - create_unit, destroy_unit
  - set_unit_position, get_unit_position
  - fire_weapon, apply_damage
  - set_threat_level, query_threats
  - sync_hla_federation

AVSimAdapter (7505):
  - spawn_vehicle, destroy_vehicle
  - set_vehicle_control, get_vehicle_state
  - set_sensor_config, get_sensor_data
  - apply_traffic_rules, plan_route
  - detect_obstacle, compute_path

ScientificSimAdapter (7506):
  - set_simulation_params, get_simulation_state
  - run_timestep, pause_simulation
  - get_field_data, set_field_data
  - apply_boundary_condition
  - export_results_to_file

WebBridge (7507):
  - get_scene_as_threejs, get_scene_as_babylon
  - set_camera_view, get_camera_view
  - enable_orbit_controls, enable_fps_controls
  - capture_screenshot, record_video
  - export_gltf

StarlinkAdapter (7508):
  - simulate_satellite_coverage
  - compute_link_latency
  - get_network_topology
  - simulate_packet_loss
  - get_signal_strength

HLAFederateBridge (7509):
  - publish_interaction
  - subscribe_to_interaction
  - update_object_attributes
  - query_federation_state
  - synchronize_federation

Port Assignments (7100-7509):
  7100 - UnrealAdapter (Unreal Engine)
  7200 - BlenderAdapter (Blender 4.x)
  7300 - OmniverseConnector (NVIDIA Omniverse)
  7400 - RobloxHTTPAdapter (Roblox)
  7500 - GodotAdapter (Godot 4.x)
  7501 - Godot4Bridge (Godot 4.x native)
  7502 - O3DEAdapter (Amazon O3DE)
  7503 - UnityAdapter (Unity Engine)
  7504 - MilitarySimAdapter (HLA/RTI)
  7505 - AVSimAdapter (Autonomous vehicles)
  7506 - ScientificSimAdapter (Scientific computing)
  7507 - WebBridge (Web 3D viewers)
  7508 - StarlinkAdapter (Satellite networks)
  7509 - HLAFederateBridge (HLA Federation)
  8000 - RobloxHTTPAdapter (HTTP legacy)

Implementation Order (Priority):
  1. GodotAdapter (7500) - Most requested
  2. UnityAdapter (7503) - Most common game engine
  3. Godot4Bridge (7501) - Native Godot support
  4. O3DEAdapter (7502) - AWS/Lumberyard
  5. WebBridge (7507) - Browser accessibility
  6. AVSimAdapter (7505) - Autonomous systems
  7. MilitarySimAdapter (7504) - Specialized use case
  8. ScientificSimAdapter (7506) - Research community
  9. StarlinkAdapter (7508) - Satellite networks
 10. HLAFederateBridge (7509) - Federation standards

Total Commands Target: 150+ across all adapters
"""
