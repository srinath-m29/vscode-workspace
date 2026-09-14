.PHONY: all c cpp py clean

all: c cpp py

c:
	gcc hello.c -o hello_c
	./hello_c

cpp:
	g++ hello.cpp -o hello_cpp
	./hello_cpp

py:
	python3 hello.py

clean:
	rm -f hello_c hello_cpp
