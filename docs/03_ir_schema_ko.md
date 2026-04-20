# Krita Native Illustration Compiler v0 IR 스키마

## 1. 최상위 구조

```json
{
  "meta": {},
  "document": {},
  "resources": [],
  "layers": [],
  "exports": []
}
```

## 2. 공통 규칙

- JSON은 사람이 읽기 쉬운 형태를 유지한다.
- `layers`와 `children` 순서는 bottom-to-top이다.
- `opacity`는 `0.0`부터 `1.0`까지의 정규화 값이 기본이다.
- 편의를 위해 `0..255` 정수도 받아 내부에서 정규화한다.
- v0 구현은 안정성을 위해 `document.color_model="RGBA"`, `document.color_depth="U8"`만 허용한다.

## 3. `document`

```json
{
  "width": 2048,
  "height": 2048,
  "dpi": 300,
  "color_model": "RGBA",
  "color_depth": "U8",
  "background_color": "#FFF7F4FF",
  "file_name": "anime_bust_demo"
}
```

## 4. `resources`

```json
[
  {
    "id": "face_base_png",
    "kind": "png",
    "path": "assets/face_base.png"
  },
  {
    "id": "sparkle_svg",
    "kind": "svg",
    "path": "assets/sparkle.svg"
  }
]
```

- `kind` 지원값: `png`, `svg`
- `path`는 workspace root 이하 경로여야 한다.

## 5. 레이어 공통 구조

```json
{
  "id": "lineart",
  "name": "lineart",
  "type": "paint",
  "visible": true,
  "opacity": 1.0,
  "blend_mode": "normal",
  "locked": false,
  "alpha_locked": false,
  "inherit_alpha": false,
  "tags": ["character"],
  "ops": [],
  "masks": [],
  "children": []
}
```

## 6. 레이어 타입

### `group`

- `children` 사용 가능
- `ops`는 비워 두는 것을 원칙으로 한다

### `paint`

- `ops` 지원
- `children` 없음
- `masks` 가능

### `vector`

- `ops`는 `add_svg`만 허용
- `children` 없음
- `masks` 가능

### `imported_raster`

- 외부 PNG를 수정 가능한 paint layer로 들여오기 위한 특수 타입
- `ops`는 `import_png` 중심
- 내부 생성 노드는 paint layer

## 7. paint/imported_raster ops

### `fill_solid`

```json
{
  "type": "fill_solid",
  "color": "#F6E1D5FF",
  "x": 0,
  "y": 0,
  "width": 512,
  "height": 512
}
```

- 좌표를 생략하면 문서 전체를 채운다.

### `put_pixels`

```json
{
  "type": "put_pixels",
  "x": 10,
  "y": 12,
  "rows": [
    ["#00000000", "#FFFFFFFF"],
    ["#FFFFFFFF", "#00000000"]
  ]
}
```

### `import_png`

```json
{
  "type": "import_png",
  "resource_id": "face_base_png",
  "x": 128,
  "y": 256
}
```

### `brush_line`

```json
{
  "type": "brush_line",
  "from": [100, 120],
  "to": [300, 120],
  "color": "#202020FF",
  "size": 6.0
}
```

### `brush_path`

```json
{
  "type": "brush_path",
  "points": [[100, 100], [130, 80], [180, 120]],
  "color": "#202020FF",
  "size": 4.0
}
```

## 8. vector ops

### `add_svg`

```json
{
  "type": "add_svg",
  "resource_id": "sparkle_svg"
}
```

또는

```json
{
  "type": "add_svg",
  "svg": "<svg ...>...</svg>"
}
```

## 9. mask

```json
{
  "id": "flats_clip",
  "name": "flats_clip",
  "type": "selection_mask",
  "visible": true,
  "selection": {
    "rectangles": [
      {"x": 320, "y": 240, "width": 900, "height": 1200, "value": 255}
    ]
  }
}
```

### 지원 mask type

- `selection_mask`
- `transparency_mask`
- `transform_mask`

### `selection`

```json
{
  "rectangles": [
    {"x": 10, "y": 10, "width": 100, "height": 100, "value": 255}
  ],
  "pixel_data": {
    "x": 0,
    "y": 0,
    "width": 2,
    "height": 2,
    "values": [0, 255, 255, 0]
  }
}
```

`transform_mask`는 v0에서 생성 자체를 보장하고, 상세 transform 적용은 unsupported로 기록할 수 있다.

## 10. `exports`

```json
[
  {"kind": "kra", "file_name": "demo.kra", "enabled": true},
  {"kind": "png", "file_name": "demo_preview.png", "enabled": true},
  {"kind": "psd", "file_name": "demo.psd", "enabled": false}
]
```

- `kind` 지원값: `kra`, `png`, `psd`
- `kra`와 `png`는 기본 권장 export다.
- 실제 저장 디렉터리는 compile 시점의 output root 정책이 결정하고, 여기의 `file_name`은 주로 leaf filename으로 해석한다.
