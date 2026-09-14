import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { countries } from '../data/demo.js';

function point(lat, lon, radius = 1) {
  const phi = (90 - lat) * Math.PI / 180, theta = (lon + 180) * Math.PI / 180;
  return new THREE.Vector3(-radius * Math.sin(phi) * Math.cos(theta), radius * Math.cos(phi), radius * Math.sin(phi) * Math.sin(theta));
}
export default function Globe({ selected = [], tones = [], onCountry, focus, spinning }) {
  const mount = useRef(null), labels = useRef({}), api = useRef(null), callback = useRef(onCountry);
  const [failed, setFailed] = useState(false);
  callback.current = onCountry;
  useEffect(() => {
    const host = mount.current;
    let renderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); } catch { setFailed(true); return; }
    let dead = false, raf;
    const scene = new THREE.Scene(), group = new THREE.Group(); scene.add(group);
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 50); camera.position.z = 3.6;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputEncoding = THREE.sRGBEncoding;
    host.prepend(renderer.domElement);
    const globeGeometry = new THREE.SphereGeometry(1, 64, 64);
    const material = new THREE.MeshPhongMaterial({ color: 0x80948d, shininess: 4 });
    group.add(new THREE.Mesh(globeGeometry, material));
    const texture = new THREE.TextureLoader().load('/earth.jpg', () => { if (!dead) { texture.encoding = THREE.sRGBEncoding; material.map = texture; material.needsUpdate = true; } });
    const grid = new THREE.Mesh(new THREE.SphereGeometry(1.008, 36, 18), new THREE.MeshBasicMaterial({ color: 0xa4cbbd, wireframe: true, transparent: true, opacity: .055 })); group.add(grid);
    scene.add(new THREE.AmbientLight(0xd7e8ef, .92));
    const light = new THREE.DirectionalLight(0xf3ffe4, 1.05); light.position.set(-3, 3, 4); scene.add(light);
    const glow = new THREE.Mesh(new THREE.SphereGeometry(1.035, 48, 48), new THREE.ShaderMaterial({ transparent: true, side: THREE.BackSide, blending: THREE.AdditiveBlending, vertexShader: 'varying vec3 n; varying vec3 v; void main(){ n=normalize(normalMatrix*normal); vec4 p=modelViewMatrix*vec4(position,1.); v=normalize(-p.xyz); gl_Position=projectionMatrix*p; }', fragmentShader: 'varying vec3 n; varying vec3 v; void main(){float a=pow(1.-abs(dot(n,v)),3.); gl_FragColor=vec4(.38,.66,.58,a*.6);}' })); group.add(glow);
    const pins = countries.map(c => {
      const p = point(c.lat, c.lon, 1.024);
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(.018, 12, 12), new THREE.MeshBasicMaterial({ color: 0xd5f5a0 })); mesh.position.copy(p); mesh.userData.code = c.code; group.add(mesh);
      return { ...c, mesh, point: p };
    });
    let targetY = -2.25, targetX = .18, spin = false, drag = null;
    group.rotation.set(targetX, targetY, 0);
    const resize = () => { const w = host.clientWidth, h = host.clientHeight; if (!w || !h) return; renderer.setSize(w, h); camera.aspect = w / h; camera.position.z = camera.aspect < 1 ? 4.2 : 3.6; camera.updateProjectionMatrix(); };
    const observer = new ResizeObserver(resize); observer.observe(host); resize();
    const down = e => { drag = { x: e.clientX, y: e.clientY }; renderer.domElement.setPointerCapture(e.pointerId); };
    const move = e => { if (!drag) return; targetY += (e.clientX - drag.x) * .006; targetX = Math.max(-.7, Math.min(.7, targetX + (e.clientY - drag.y) * .004)); drag = { x: e.clientX, y: e.clientY }; };
    const up = () => { drag = null; };
    renderer.domElement.addEventListener('pointerdown', down); renderer.domElement.addEventListener('pointermove', move); renderer.domElement.addEventListener('pointerup', up); renderer.domElement.addEventListener('pointercancel', up);
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    function loop() {
      if (dead) return;
      raf = requestAnimationFrame(loop);
      if (spin && !drag && !reduced.matches) targetY += .001;
      group.rotation.y += (targetY - group.rotation.y) * (reduced.matches ? 1 : .07);
      group.rotation.x += (targetX - group.rotation.x) * (reduced.matches ? 1 : .07);
      group.updateMatrixWorld();
      pins.forEach(pin => {
        const label = labels.current[pin.code]; if (!label) return;
        const world = pin.point.clone().applyMatrix4(group.matrixWorld), projected = world.clone().project(camera);
        const visible = world.z > .13;
        label.style.visibility = visible ? 'visible' : 'hidden';
        label.style.left = `${(projected.x * .5 + .5) * host.clientWidth}px`;
        label.style.top = `${(-projected.y * .5 + .5) * host.clientHeight}px`;
      });
      renderer.render(scene, camera);
    }
    api.current = {
      focus(code) { const country = countries.find(c => c.code === code); if (!country) return; const p = point(country.lat, country.lon); const next = -Math.atan2(p.x, p.z); targetY = group.rotation.y + Math.atan2(Math.sin(next - group.rotation.y), Math.cos(next - group.rotation.y)); targetX = country.lat * Math.PI / 180 * .7; },
      spin(value) { spin = value; },
      colors(rows, selection) { pins.forEach(pin => { const tone = rows.find(r => r.code === pin.code); const enough = tone?.count >= 30; pin.mesh.material.color.set(tone ? !enough ? '#94a7ba' : tone.average <= 33 ? '#ed9379' : tone.average > 66 ? '#c7ef7d' : '#e3c77e' : '#c7ef7d'); pin.mesh.scale.setScalar(selection.includes(pin.code) ? 1.65 : 1); }); },
    };
    loop();
    return () => { dead = true; cancelAnimationFrame(raf); observer.disconnect(); api.current = null; renderer.domElement.removeEventListener('pointerdown', down); renderer.domElement.removeEventListener('pointermove', move); renderer.domElement.removeEventListener('pointerup', up); renderer.domElement.removeEventListener('pointercancel', up); scene.traverse(o => { o.geometry?.dispose(); o.material?.dispose(); }); texture.dispose(); renderer.dispose(); renderer.domElement.remove(); };
  }, []);
  useEffect(() => { if (focus) api.current?.focus(focus); }, [focus]);
  useEffect(() => { api.current?.spin(spinning); }, [spinning]);
  useEffect(() => { api.current?.colors(tones, selected); }, [tones, selected]);
  return <div className="globe-canvas" ref={mount} aria-label="국가를 선택하는 지구본">
    {!failed && countries.map(c => <button key={c.code} ref={el => { labels.current[c.code] = el; }} className={`map-label ${selected.includes(c.code) ? 'selected' : ''}`} onClick={() => callback.current(c.code)} tabIndex={-1}><i />{c.name}</button>)}
    {failed && <div className="globe-fallback"><span>◎</span><p>지구본을 표시할 수 없습니다.<br/>아래 국가 버튼으로 동일하게 탐색하세요.</p></div>}
  </div>;
}
