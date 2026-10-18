# WingDesk 업데이트 배포

WingDesk Windows 프로그램의 실행 파일과 자동 업데이트 안내를 배포합니다.

## 최초 설치

[WingDesk 1.5.8 실행 ZIP 다운로드](https://raw.githubusercontent.com/lookitoone/wingdesk-release/main/packages/WingDesk-1.5.8.zip)

압축을 풀고 WingDeskLauncher.exe를 실행하세요. 기존 런처가 열려 있다면 먼저 종료하세요. 처음 한 번 새 런처를 설치한 뒤 같은 바탕화면 런처를 사용합니다. 별도 Python 설치나 관리자 권한은 필요하지 않습니다. 첫 실행에는 인터넷 연결이 필요합니다.

## 이후 업데이트

런처가 새 버전을 확인합니다. ‘업데이트하고 실행’을 누르면 다운로드·검사·설치 후 새 버전을 엽니다. 상품 등록·수집·주문 작업 중에는 먼저 작업을 마치라는 안내를 표시합니다. 상품·계정 데이터는 사용자 PC에 유지합니다.

[고정 업데이트 안내](https://raw.githubusercontent.com/lookitoone/wingdesk-release/main/update.json)

## 배포자

새 버전은 packages/WingDesk-버전.zip의 새 경로에 저장합니다. 기존 버전 파일은 덮어쓰지 않습니다. 최종 ZIP의 실제 크기와 SHA-256으로 update.json을 만들고 ZIP과 함께 하나의 커밋에 반영하세요. GitHub CDN 반영에 짧은 지연이 있을 수 있습니다.

개별 소스 ZIP이나 사용자 DB·계정 파일은 이 저장소에 업로드하지 않습니다. 실행 EXE 자체에는 기존 구조에 따라 Python 소스가 내장되어 있습니다.

## 검증 범위

1.5.8: Python 검사 286개와 Chromium UI 흐름을 통과했습니다. 실제 배포 파일의 버전·크기·해시를 검증합니다. Windows 실기기의 준비 화면·바로가기·프로세스 실행 전환과 실제 판매자 API 동작은 별도 확인이 필요합니다.

1.5.8은 내장 Python의 격리 실행 경로 누락으로 런처가 코드 1로 종료되는 문제를 수정합니다. 초기 모듈 로딩 오류도 준비 화면과 launcher-startup-error.log에 기록합니다. 기존 오류 준비창을 닫고 새 WingDeskLauncher.exe를 실행하세요.
