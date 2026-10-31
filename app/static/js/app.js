(function () {
  "use strict";

  // Confirm before destructive form submissions.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // Loading state while the tailored resume is generated.
  var generateForm = document.getElementById("generate-form");
  if (generateForm) {
    generateForm.addEventListener("submit", function () {
      var btn = document.getElementById("generate-btn");
      var note = document.getElementById("generate-loading");
      setTimeout(function () {
        btn.disabled = true;
        btn.textContent = "Generating…";
        note.hidden = false;
      }, 0);
    });
  }

  var form = document.getElementById("analyze-form");
  if (!form) return;

  var zone = document.getElementById("dropzone");
  var input = document.getElementById("resume");
  var fileName = document.getElementById("file-name");
  var errorBox = document.getElementById("resume-error");
  var maxBytes = parseInt(zone.dataset.maxBytes, 10);

  function fileProblem(file) {
    if (!file) return "Please choose a resume file (PDF or DOCX).";
    if (!/\.(pdf|docx)$/i.test(file.name)) return "Unsupported file type. Please upload a .pdf or .docx file.";
    if (file.size === 0) return "The selected file is empty.";
    if (file.size > maxBytes) return "The file is too large. Maximum size is " + (maxBytes / 1048576) + " MB.";
    return "";
  }

  function showFile() {
    var file = input.files && input.files[0];
    fileName.textContent = file ? file.name + " (" + Math.ceil(file.size / 1024) + " KB)" : "";
    errorBox.textContent = file ? fileProblem(file) : "";
  }

  input.addEventListener("change", showFile);

  ["dragenter", "dragover"].forEach(function (name) {
    zone.addEventListener(name, function (event) {
      event.preventDefault();
      zone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach(function (name) {
    zone.addEventListener(name, function (event) {
      event.preventDefault();
      zone.classList.remove("dragover");
    });
  });
  zone.addEventListener("drop", function (event) {
    if (event.dataTransfer && event.dataTransfer.files.length) {
      input.files = event.dataTransfer.files;
      showFile();
    }
  });

  form.addEventListener("submit", function (event) {
    var problem = fileProblem(input.files && input.files[0]);
    if (problem) {
      event.preventDefault();
      errorBox.textContent = problem;
      input.focus();
      return;
    }
    var button = document.getElementById("submit-btn");
    var loading = document.getElementById("loading");
    // Disable after the browser has started the submit.
    setTimeout(function () {
      button.disabled = true;
      loading.hidden = false;
    }, 0);
  });
})();
