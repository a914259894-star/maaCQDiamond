from pathlib import Path

import shutil

assets_dir = Path(__file__).parent.parent.resolve() / "assets"


def configure_ocr_model():
    ocr_dir = assets_dir / "resource" / "model" / "ocr"
    # 项目已自带 OCR 模型时优先使用（与开发/测试阶段的模型保持一致）
    if ocr_dir.exists():
        print("Found existing OCR directory, skipping default OCR model import.")
        return

    assets_ocr_dir = assets_dir / "MaaCommonAssets" / "OCR"
    if not assets_ocr_dir.exists():
        print(f"File Not Found: {assets_ocr_dir}")
        print("请初始化子模块（git submodule update --init --recursive），"
              "或手动放置 OCR 模型到 assets/resource/model/ocr。")
        exit(1)

    shutil.copytree(
        assets_ocr_dir / "ppocr_v6" / "small",
        ocr_dir,
        dirs_exist_ok=True,
    )


if __name__ == "__main__":
    configure_ocr_model()

    print("OCR model configured.")
