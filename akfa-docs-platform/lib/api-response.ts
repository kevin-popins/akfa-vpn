import { NextResponse } from 'next/server';

export function ok<T>(data: T) {
  return NextResponse.json(data);
}

export function error(message: string, status = 400) {
  return NextResponse.json({ message }, { status });
}

export function unauthorized() {
  return error('Нужно войти в админку', 401);
}
