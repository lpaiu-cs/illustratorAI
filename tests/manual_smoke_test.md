# Manual Smoke Test

## Environment

- Krita 5.3.1 desktop
- Plugin path contains [pykrita/native_illustration_compiler.desktop](/Users/lpaiu/vs/lab/illustratorAI_krita/pykrita/native_illustration_compiler.desktop) and [pykrita/native_illustration_compiler](/Users/lpaiu/vs/lab/illustratorAI_krita/pykrita/native_illustration_compiler)
- Repository `src` directory is accessible to the plugin

## Steps

1. Run [install_plugin_dev_mac.sh](/Users/lpaiu/vs/lab/illustratorAI_krita/scripts/dev/install_plugin_dev_mac.sh).
2. Open Krita and enable `Native Illustration Compiler` in Python Plugin Manager.
3. Restart Krita.
4. Run `Tools -> Scripts -> Compile Bundled Demo`.
5. Pick `demo_anime_bust.json`.
6. Choose an output directory or cancel to use the default dev output root under `.nic_dev_build/demo_anime_bust`.
7. Confirm that a new document opens and `.kra`, preview PNG, and compile report are produced in the selected output root.
8. Save and reopen the generated `.kra`.
9. Verify layer names, order, visibility, opacity, blend mode, masks, and vector layer presence.
10. Run `Tools -> Scripts -> Export Active Document Manifest`.
11. Confirm manifest JSON is written and the current document tree is serialized.

## Expected Checks

- `background`, `character`, `sketch`, `lineart`, `flats`, `shadows`, `highlights`, `accessories` are present.
- `character_selection`, `shadow_mask`, `highlight_transform` masks exist.
- `accessories` remains a vector layer.
- Preview PNG exports without flattening away the `.kra` source.
- Compile report contains `run_mode`, `environment`, `capability`, `path_resolution`, and `compile_summary`.
- If brush APIs are missing, compile still finishes and the report records fallback or unsupported entries.
