"""
초기 관리자 계정 생성 스크립트 (승인까지 한 번에 처리)
사용법: python create_admin_user.py [username] [password]
"""
import sys
from repo.user_repo import create_user, approve_user

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("사용법: python create_admin_user.py [username] [password]")
        print("예시: python create_admin_user.py admin admin123")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]

    try:
        if create_user(username, password):
            approve_user(username, "admin", "script")
            print(f"관리자 '{username}' 생성 및 승인 완료!")
        else:
            print(f"사용자 '{username}'가 이미 존재합니다.")
    except Exception as e:
        print(f"오류 발생: {e}")
        sys.exit(1)
