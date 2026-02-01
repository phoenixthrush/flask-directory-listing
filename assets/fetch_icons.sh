curl -s https://www.apache.org/icons/ | sed -n 's/.*href="\([^"]*\)".*/https:\/\/www.apache.org\/icons\/\1/p' | xargs -n1 curl -O
