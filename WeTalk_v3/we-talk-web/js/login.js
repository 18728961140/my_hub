/* ============================================================
   登录页交互
   ============================================================ */

const loginForm = document.getElementById("loginForm");
const usernameInput = document.getElementById("username");
const passwordInput = document.getElementById("password");
const rememberInput = document.getElementById("remember");
const loginError = document.getElementById("loginError");

loginForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  const remember = rememberInput.checked;

  if (!username || !password) {
    loginError.textContent = "请输入用户名和密码";
    return;
  }

  const result = login(username, password, remember);
  if (result.ok) {
    loginError.textContent = "";
    location.replace("chat.html");
  } else {
    loginError.textContent = result.message;
    passwordInput.value = "";
    passwordInput.focus();
  }
});
