# Code Examples for MockFactory

## Python
```python
print("Hello from MockFactory!")
print("2 + 2 =", 2 + 2)

# List comprehension
squares = [x**2 for x in range(10)]
print("Squares:", squares)
```

## JavaScript/Node.js
```javascript
console.log("Hello from MockFactory!");
console.log("2 + 2 =", 2 + 2);

// Array operations
const squares = Array.from({length: 10}, (_, i) => i ** 2);
console.log("Squares:", squares);
```

## PHP
```php
<?php
echo "Hello from MockFactory!\n";
echo "2 + 2 = " . (2 + 2) . "\n";

// Array operations
$squares = array_map(function($x) { return $x ** 2; }, range(0, 9));
echo "Squares: " . json_encode($squares) . "\n";
?>
```

## Go
```go
package main

import "fmt"

func main() {
    fmt.Println("Hello from MockFactory!")
    fmt.Println("2 + 2 =", 2+2)

    // Squares
    squares := make([]int, 10)
    for i := 0; i < 10; i++ {
        squares[i] = i * i
    }
    fmt.Println("Squares:", squares)
}
```

## Shell
```bash
echo "Hello from MockFactory!"
echo "2 + 2 = $((2 + 2))"
echo "Current directory: $(pwd)"
echo "User: $(whoami)"
```

## Perl
```perl
print "Hello from MockFactory!\n";
print "2 + 2 = ", 2 + 2, "\n";

# Array operations
my @squares = map { $_ ** 2 } 0..9;
print "Squares: @squares\n";
```

## Security Test Examples

### Attempt to access /proc (should be blocked)
```python
import os
try:
    print(os.listdir('/proc'))
except Exception as e:
    print(f"Blocked: {e}")
```

### Attempt network access (should fail)
```python
import urllib.request
try:
    urllib.request.urlopen('http://google.com')
except Exception as e:
    print(f"Network blocked: {e}")
```

### Attempt to write to root (should fail)
```python
try:
    with open('/test.txt', 'w') as f:
        f.write('test')
except Exception as e:
    print(f"Write blocked: {e}")
```

### Attempt to run as root (should fail)
```bash
whoami
id
ls -la /root 2>&1 || echo "Root access blocked"
```

### Memory limit test
```python
# This should be limited by container constraints
data = []
try:
    for i in range(1000000):
        data.append([0] * 1000)
except MemoryError:
    print("Memory limit reached (expected)")
```

## API Test Examples

### cURL: Execute Python code
```bash
curl -X POST http://localhost:8000/api/v1/code/execute \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: test-session-123" \
  -d '{
    "language": "python",
    "code": "print(\"Hello from cURL!\")"
  }'
```

### cURL: Sign up
```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "securepassword123"
  }'
```

### cURL: Sign in
```bash
curl -X POST http://localhost:8000/api/v1/auth/signin \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "securepassword123"
  }'
```

### cURL: Check usage
```bash
curl -X GET http://localhost:8000/api/v1/code/usage \
  -H "X-Session-Id: test-session-123"
```

### cURL: Execute with authentication
```bash
TOKEN="your-jwt-token-here"

curl -X POST http://localhost:8000/api/v1/code/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "language": "python",
    "code": "import sys; print(sys.version)"
  }'
```
