## 자체학습모델(self-hosted model) 연동 예정 자리.
## 아직 설계 중이라 ingestion/loader.py에 있던 흔적을 이 폴더로 옮겨 보관합니다.
## 학습 관련 코드는 model/model.py 참고.


# 수정 필요
def model_loader():
    return 0


## llm.py의 get_llm()에 있던 "self" provider 분기 원본.
## 자체 모델 연동이 확정되면 아래 분기를 llm.py로 복원하고 model_loader를 구현합니다.
#
# elif provider == "self":
#     ## 직접만들 모델 사용
#     return -1
