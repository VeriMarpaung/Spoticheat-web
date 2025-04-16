document.addEventListener("DOMContentLoaded", () => {
  const loginBtn = document.getElementById("login-btn");
  const playlistSelect = document.getElementById("playlist-select");
  const trackList = document.getElementById("track-list");
  const statusMsg = document.getElementById("status-msg");
  const spinner = document.getElementById("spinner");
  const resultBox = document.getElementById("result-box");
  const usernameBox = document.getElementById("username");

  loginBtn?.addEventListener("click", () => {
    fetch("/login_url")
      .then(res => res.json())
      .then(data => {
        window.location.href = data.url;
      })
      .catch(err => {
        statusMsg.innerText = "⚠️ Gagal login. Coba lagi.";
        console.error(err);
      });
  });

  playlistSelect?.addEventListener("change", () => {
    const selected = playlistSelect.value;
    fetch("/select_playlist", {
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ playlist: selected })
    })
      .then(res => res.json())
      .then(data => {
        trackList.innerHTML = '';
        data.tracks.forEach((track, index) => {
          const div = document.createElement("div");
          const cb = document.createElement("input");
          cb.type = "checkbox";
          cb.id = "cb" + index;
          cb.value = track.url;

          const label = document.createElement("label");
          label.htmlFor = cb.id;
          label.innerText = `${track.name} by ${track.artist}`;

          div.appendChild(cb);
          div.appendChild(label);
          trackList.appendChild(div);
        });
        document.getElementById("download-selected").disabled = false;
        document.getElementById("download-all").disabled = false;
      })
      .catch(err => {
        statusMsg.innerText = "⚠️ Gagal mengambil track.";
        console.error(err);
      });
  });

  document.getElementById("download-selected")?.addEventListener("click", () => {
    const selected = Array.from(document.querySelectorAll("#track-list input[type='checkbox']:checked"))
      .map(cb => cb.value);
    if (selected.length === 0) {
      statusMsg.innerText = "❗Pilih lagu terlebih dahulu.";
      return;
    }
    downloadTracks(selected);
  });

  document.getElementById("download-selected").disabled = true;
  document.getElementById("download-all").disabled = true;

  document.getElementById("download-all")?.addEventListener("click", () => {
    const allTracks = Array.from(document.querySelectorAll("#track-list input[type='checkbox']"))
      .map(cb => cb.value);
    downloadTracks(allTracks);
  });

  function downloadTracks(trackList) {
    spinner.classList.remove("hidden");
    statusMsg.innerText = "Downloading...";
    resultBox.innerText = "";

    fetch("/download", {
      method: "POST",
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tracks: trackList })
    })
      .then(res => res.json())
      .then(data => {
        spinner.classList.add("hidden");
        statusMsg.innerText = "Download complete!";
        resultBox.innerText = data.results.join('\n') || "Tidak ada lagu yang berhasil didownload.";

        // Aktifkan kembali tombol setelah selesai
        document.getElementById("download-selected").disabled = false;
        document.getElementById("download-all").disabled = false;
      })
      .catch(err => {
        spinner.classList.add("hidden");
        statusMsg.innerText = "❌ Gagal mendownload lagu.";
        console.error(err);
      });
  }

  function fetchUserInfo() {
    fetch('/user_info')
      .then(res => res.json())
      .then(data => {
        if (data.logged_in && data.username) {
          usernameBox.classList.remove('hidden');
          usernameBox.textContent = `🎵 Logged in as ${data.username}`;
        }
      })
      .catch(err => {
        console.warn("Gagal ambil user info:", err);
      });
  }

  fetchUserInfo();
});
