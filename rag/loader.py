from pathlib import Path
import json

from langchain_core.documents import Document


def json_loader(json_path_list, limit=-1):
    """
    JSON 파일을 읽어서 Document로 감싸기만 하는 로더.
    필드 파싱/텍스트 조합은 하지 않음 (스키마 변경에 안전하게 만들기 위함).
    """
    json_docs = []

    for p in json_path_list:
        if limit > -1 and len(json_docs) >= limit:
            break

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        recipe_id = str(data.get("recipe_id") or data.get("seq") or p.stem)
        doc = Document(
            page_content=json.dumps(data, ensure_ascii=False),
            metadata={
                "source": str(p),
                "seq": recipe_id,
                "doc_id": f"json:{recipe_id}",  # VDB 중복 방지용 고유 ID (레시피 ID 기반)
            },
        )

        preview = str(data)[:40].replace("\n", " ")
        print(f"[{p.name}] {preview}...")
        json_docs.append(doc)

    print(f"로딩된 전체 JSON Document 파일 수: {len(json_docs)}")
    return json_docs


def fileloader_distributor(limit=-1):
    processed_dir = Path(__file__).resolve().parent.parent / "data_pipeline" / "structured_recipes"

    json_path_list = sorted(processed_dir.glob("*.json"))
    json_docs = json_loader(json_path_list, limit=limit)

    return json_docs
