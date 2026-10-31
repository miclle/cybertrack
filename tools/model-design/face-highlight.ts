import * as THREE from 'three';
import type { PreviewFace } from './types.js';

export function faceAt(faces: PreviewFace[] | undefined, triangle: number): PreviewFace | undefined {
  return faces?.find(face=>triangle>=face.start && triangle<face.start+face.count);
}

// Overlays retain depth testing, so hidden faces never shine through the model.
export function faceHighlight(scene: THREE.Scene, color: string, opacity: number) {
  const material=new THREE.MeshBasicMaterial({color,transparent:true,opacity,depthWrite:false,
    polygonOffset:true,polygonOffsetFactor:-2,polygonOffsetUnits:-2,side:THREE.DoubleSide});
  const overlay=new THREE.Mesh(new THREE.BufferGeometry(),material);
  overlay.visible=false;overlay.renderOrder=2;scene.add(overlay);
  let key='';
  return {
    clear() {key='';overlay.visible=false;},
    show(mesh: THREE.Mesh, triangle: number, face?: PreviewFace) {
      const next=mesh.geometry.uuid+':'+(face?.id ?? triangle);
      if(key!==next) {
        const geometry=new THREE.BufferGeometry();
        geometry.setAttribute('position',mesh.geometry.getAttribute('position'));
        const start=(face?.start ?? triangle)*3, count=(face?.count ?? 1)*3;
        geometry.setIndex(Array.from(mesh.geometry.index!.array.slice(start,start+count)));
        overlay.geometry.dispose();overlay.geometry=geometry;key=next;
      }
      overlay.position.copy(mesh.position);overlay.quaternion.copy(mesh.quaternion);
      overlay.scale.copy(mesh.scale);overlay.visible=true;
    },
  };
}
