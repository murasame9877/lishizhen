(() => {
  const nav = document.getElementById('nav');
  const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 24);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });

  // Scroll reveal
  const revealItems = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('in');
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );
    revealItems.forEach((el) => io.observe(el));
  } else {
    revealItems.forEach((el) => el.classList.add('in'));
  }

  // Dynamic flow
  const steps = Array.from(document.querySelectorAll('.step'));
  const scenes = Array.from(document.querySelectorAll('.scene'));
  const caption = document.getElementById('caption');
  const progress = document.getElementById('progress');
  const shell = document.querySelector('.flow-shell');
  if (!steps.length || !scenes.length) return;

  const captions = [
    '消息在哪里，日程就从哪里长出来。',
    '时间、地点、截止：先把中文读懂。',
    '编号、冲突、改删：确认后再写日历。',
    '一次写入，手机自己完成之后的所有提醒。',
    '到点弹窗，不依赖后台常驻。',
  ];
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let current = 0;
  let timer = null;
  let paused = false;

  function setStep(index, userInitiated) {
    current = (index + steps.length) % steps.length;
    steps.forEach((s, i) => s.classList.toggle('active', i === current));
    scenes.forEach((s, i) => s.classList.toggle('active', i === current));
    if (caption) caption.textContent = captions[current];
    if (progress) progress.style.width = `${((current + 1) / steps.length) * 100}%`;
    if (userInitiated) restart();
  }

  function tick() {
    if (!paused) setStep(current + 1);
  }

  function restart() {
    if (timer) clearInterval(timer);
    timer = null;
    if (!reduced) timer = setInterval(tick, 3200);
  }

  steps.forEach((step, i) => {
    step.addEventListener('click', () => setStep(i, true));
    step.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setStep(i, true);
      }
    });
    step.tabIndex = 0;
    step.setAttribute('role', 'button');
  });

  shell?.addEventListener('mouseenter', () => { paused = true; });
  shell?.addEventListener('mouseleave', () => { paused = false; });
  shell?.addEventListener('focusin', () => { paused = true; });
  shell?.addEventListener('focusout', () => { paused = false; });

  setStep(0);
  restart();

  // Start the cycle only when the flow enters the viewport
  if ('IntersectionObserver' in window && !reduced) {
    const flowObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) restart();
        else if (timer) { clearInterval(timer); timer = null; }
      });
    }, { threshold: 0.25 });
    flowObserver.observe(shell);
  }
})();
