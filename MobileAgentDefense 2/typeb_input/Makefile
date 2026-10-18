.PHONY: build deploy doctor test check
build:
	bash scripts/build.sh
deploy:
	bash scripts/deploy.sh
doctor:
	python3 -m guiagent_touch doctor
test:
	python3 -m unittest discover -s tests -v
check:
	python3 scripts/check_release.py
