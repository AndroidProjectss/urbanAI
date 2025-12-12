from building_optimizer.models import School

# Анализ данных школ
total = School.objects.count()
no_capacity = School.objects.filter(max_capacity=0, real_capacity=0).count()
no_students = School.objects.filter(total_students=0).count()
both_missing = School.objects.filter(max_capacity=0, real_capacity=0, total_students=0).count()
capacity_but_no_students = School.objects.filter(total_students=0).exclude(max_capacity=0).count()
students_but_no_capacity = School.objects.filter(max_capacity=0, real_capacity=0).exclude(total_students=0).count()

print(f"📊 Статистика данных школ:")
print(f"=" * 60)
print(f"Всего школ: {total}")
print(f"\n❌ Отсутствующие данные:")
print(f"  • Без вместимости: {no_capacity} ({round(no_capacity/total*100, 1)}%)")
print(f"  • Без данных об учениках: {no_students} ({round(no_students/total*100, 1)}%)")
print(f"  • Без обоих данных: {both_missing} ({round(both_missing/total*100, 1)}%)")
print(f"\n🔍 Детальный анализ:")
print(f"  • Есть вместимость, нет учеников: {capacity_but_no_students}")
print(f"  • Есть ученики, нет вместимости: {students_but_no_capacity}")

print(f"\n📚 Примеры школ с учениками, но без вместимости:")
print(f"=" * 60)
for s in School.objects.filter(max_capacity=0, real_capacity=0, total_students__gt=0).order_by('-total_students')[:10]:
    print(f"  • {s.name[:50]:50} | {s.total_students:4} уч. | {s.total_classes:2} кл.")

print(f"\n🏫 Среднее количество учеников на класс:")
schools_with_data = School.objects.filter(total_students__gt=0, total_classes__gt=0)
if schools_with_data.exists():
    avg_per_class = sum(s.total_students / s.total_classes for s in schools_with_data) / schools_with_data.count()
    print(f"  • {round(avg_per_class, 1)} учеников/класс (из {schools_with_data.count()} школ)")
