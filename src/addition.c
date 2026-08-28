int glob_val = 42;
static const char message[] = "fwfuzz";

int add(int a, int b) {
	return a + b;
}

int main(void) {
	return add(glob_val, message[0]);
}
